# -*- coding: utf-8 -*-
import logging
import os
import re

from babelfish import language_converters
from guessit import guessit
from requests import Session

from subliminal_patch.providers import Provider
from subliminal.providers import ParserBeautifulSoup
from subliminal import __short_version__
from subliminal.cache import SHOW_EXPIRATION_TIME, region
from subliminal.exceptions import AuthenticationError, ConfigurationError, DownloadLimitExceeded
from subliminal.score import get_equivalent_release_groups
from subliminal_patch.subtitle import Subtitle, guess_matches
from subliminal.subtitle import  fix_line_ending
from subliminal.utils import sanitize, sanitize_release_group
from subliminal.video import Episode
from subzero.language import Language


logger = logging.getLogger(__name__)

language_converters.register('subtitulamos = subliminal_patch.converters.subtitulamos:SubtitulamosConverter')

exceptions = {
'MEMENTO \d+ Mb': 'MEMENTO.480p',
'MEMENTO 1080p/720p': 'MEMENTO.1080p/MEMENTO.720p'
}



class SubtitulamosSubtitle(Subtitle):
    """Subtitulamos.tv Subtitle."""
    provider_name = 'subtitulamos'

    def __init__(self, language, series, season, episode, title, versions, download_link):
        super(SubtitulamosSubtitle, self).__init__(language)
        self.series = series
        self.season = season
        self.episode = episode
        self.title = title
        self.versions = versions
        self.download_link = download_link

    @property
    def id(self):
        return self.download_link

    def get_matches(self, video):
        matches = set()
        logger.debug('Matching: %s; %s; %s; %s; %r', self.series, self.season, self.episode, self.title, self.versions)
        # series name
        if video.series and sanitize(self.series) in (sanitize(video.series), ('%s %d' % (sanitize(video.series), video.year))):
            matches.add('series')
        # season
        if video.season and self.season == video.season:
            matches.add('season')
        # episode
        if video.episode and self.episode == video.episode:
            matches.add('episode')
        # title of the episode
        if video.title and sanitize(self.title) == sanitize(video.title):
            matches.add('title')
        # release group
        for ver in self.versions:
            release = ('%s S%dE%d x264 %s' % self.series, self.season, self.episode, ver)
            guess = guessit(release)
            if video.release_group and 'release_group' in guess and guess['release_group'] == video.release_group:
                matches.add('release_group')
                if video.resolution and ('screen_size' in guess and guess['screen_size'] == video.resolution or 'screen_size' not in guess):
                    matches.add('resolution')
                if video.source and 'format' in guess and guess['format'] == video.source:
                    matches.add('source')

        logger.debug('Matches %r, %r', self.versions, matches)
        return matches

class SubtitulamosProvider(Provider):
    """Subtitulamos.tv Provider."""
    languages = {Language(l) for l in ['ltm', 'spa', 'cat', 'glg', 'eng']}
    video_types = (Episode,)
    server_url = 'http://www.subtitulamos.tv'
    subtitle_class = SubtitulamosSubtitle

    def __init__(self):
        self.session = None

    def initialize(self):
        self.session = Session()
        self.session.headers = {'User-Agent': os.environ.get("SZ_USER_AGENT", "Sub-Zero/2")}

    def terminate(self):
        self.session.close()

    @region.cache_on_arguments(expiration_time=SHOW_EXPIRATION_TIME)
    def get_episode_id(self, series, season, episode, year=None):
        q = '%s %dx%d' % (series, season, episode)
        logger.info('Getting episode id with query %s', q)
        r = self.session.get(self.server_url + '/search/query',  params={'q': q}, timeout=10)
        r.raise_for_status()
        resultado = r.json()

        if not resultado:
            logger.error('Show not found')
            return None

        for item in resultado:
            if sanitize(item['name']) in  (sanitize(series), ('%s %d' % (sanitize(series), year))) and item['episodes'] != []:
                episode_id = item['episodes'][0]['id']
                logger.debug('Episode id %s', episode_id)
                return episode_id

        return None

    def query(self, episode_id, series, season, episode):
        # get the episode page
        logger.info('Getting the page for episode %d', episode_id)
        r = self.session.get(self.server_url + '/episodes/%d' % episode_id, timeout=10)
        soup = ParserBeautifulSoup(r.content, ['lxml', 'html.parser'])

        subtitles = []
        series = soup.select_one('.show-name').text
        ep = soup.select_one('.episode-name').text.strip().split(' - ')
        title = ep[1]
        season , episode = ep[0].split('x')
        # loop over subtitles
        row = soup.select_one('.subtitle_language')
        while row.has_attr('class'):
            if row['class'][0] == 'subtitle_language':
                language = Language.fromsubtitulamos(row.text)
            if row['class'][0] == 'compact':
                completado = row.select('.unavailable') == []
                if completado:
                    download_link = self.server_url + row.select_one('.download_subtitle').parent['href']
                    version = sanitize_release_group(row.select_one('.version_name').text)
                    for regex, info in exceptions.items():
                        re.sub(regex, info, version, flags=re.IGNORECASE)
                    versions = version.split('/')
                    subtitle = self.subtitle_class(language, series, int(season), int(episode), title, versions, download_link)
                    logger.debug('Found subtitle %r, %r', versions, language)
                    subtitles.append(subtitle)
            row = row.find_next_sibling('div')

        return subtitles



    def list_subtitles(self, video, languages):
        # lookup episode_id
        episode_id = self.get_episode_id(video.series, video.season, video.episode, video.year)

        if episode_id is not None:
            subtitles = [s for s in self.query(episode_id, video.series, video.season, video.episode)
                         if s.language in languages]
            if subtitles:
                return subtitles
        else:
            logger.error('No episode found for %r S%rE%r, year %r', video.series, video.season, video.episode, video.year)

        return []

    def download_subtitle(self, subtitle):
        # donwload the subtitle
        logger.info('Downloading subtitle %r', subtitle)
        r = self.session.get(subtitle.download_link, timeout=10)
        r.raise_for_status()

        if not r.content:
            logger.debug('Unable to download subtitle. No data returned from provider')
            return

        subtitle.content = fix_line_ending(r.content)
