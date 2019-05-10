# -*- coding: utf-8 -*-
import logging

from babelfish import language_converters
from guessit import guessit
from requests import Session

from subliminal.providers import ParserBeautifulSoup, Provider
from subliminal import __short_version__
from subliminal.cache import SHOW_EXPIRATION_TIME, region
from subliminal.exceptions import AuthenticationError, ConfigurationError, DownloadLimitExceeded
from subliminal_patch.exceptions import TooManyRequests
from subliminal.score import get_equivalent_release_groups
from subliminal.subtitle import Subtitle, fix_line_ending, guess_matches
from subliminal.utils import sanitize, sanitize_release_group
from subliminal.video import Episode
from subliminal.refiners.tvdb import TVDBClient, refine
from subzero.language import Language

logger = logging.getLogger(__name__)

language_converters.register('tusubtitulo = subliminal.converters.tusubtitulo:TuSubtituloConverter')

class TuSubtituloSubtitle(Subtitle):
    """TuSubtitulo.com Subtitle."""
    provider_name = 'tusubtitulo'

    def __init__(self, language, page_link, series, season, episode, title, year, version,
                 download_link):
        super(TuSubtituloSubtitle, self).__init__(language, page_link)
        self.series = series
        self.season = season
        self.episode = episode
        self.title = title
        self.year = year
        self.version = version
        self.download_link = download_link

    @property
    def id(self):
        return self.download_link

    def get_matches(self, video):
        matches = set()

        # series
        if video.series and sanitize(self.series) == sanitize(video.series):
            matches.add('series')
        # season
        if video.season and self.season == video.season:
            matches.add('season')
        # episode
        if video.episode and self.episode == video.episode:
            matches.add('episode')
        # title
        if video.title and sanitize(self.title) == sanitize(video.title):
            matches.add('title')
        # release_group
        if (video.release_group and self.version and
                any(r in sanitize_release_group(self.version)
                    for r in get_equivalent_release_groups(sanitize_release_group(video.release_group)))):
            matches.add('release_group')

        return matches


class TVsubtitlesProvider(Provider):
    """TVsubtitles Provider."""
    languages = {Language(l) for l in ['ltm', 'spa', 'cat', 'glg', 'eng']}
    video_types = (Episode,)
    server_url = 'http://www.tusubtitulo.com/'
    subtitle_class = TuSubtituloSubtitle

    def initialize(self):
        self.session = Session()
        self.session.headers['User-Agent'] = 'Subliminal/%s' % __short_version__

    def terminate(self):
        self.session.close()

    @region.cache_on_arguments(expiration_time=SHOW_EXPIRATION_TIME)
    def _get_show_ids(self):
        """Get the ``dict`` of show ids per series by querying the `shows.php` page.
        :return: show id per series, lower case and without quotes.
        :rtype: dict
        """
        # get the show page
        logger.info('Getting show ids')
        r = self.session.get(self.server_url + 'series.php', timeout=10)
        r.raise_for_status()
        soup = ParserBeautifulSoup(r.content, ['lxml', 'html.parser'])

        # populate the show ids
        show_ids = {}
        for show in soup.select('td.line0 > a[href^="/show/"]'):
            show_ids[show] = int(show['href'][6:])
        logger.debug('Found %d show ids', len(show_ids))

        return show_ids

    @region.cache_on_arguments(expiration_time=SHOW_EXPIRATION_TIME)
    def _search_show_id(self, series, year=None):
        """Search the show id from the `series` and `year`.
        :param str series: series of the episode.
        :param year: year of the series, if any.
        :type year: int
        :return: the show id, if found.
        :rtype: int
        """

        # build the params
        series_year = '%s %d' % (series, year) if year is not None else series

        # make the search
        logger.info('Searching show ids with %r', series_year)
        r = self.session.get(self.server_url + 'series.php', timeout=10)
        soup = ParserBeautifulSoup(r.content, ['lxml', 'html.parser'])

        show_ids = soup.select('td.line0 > a[text=series]')
        if not show_ids:
            logger.warning('Show id not found')
            return None
        show_id = int(show_ids[0]['href'][6:])
        logger.debug('Found show id %d', show_id)

        return show_id

    def get_show_id(self, series, year=None):
        """Get the best matching show id for `series`, `year` and `country_code`.
        First search in the result of :meth:`_get_show_ids` and fallback on a search with :meth:`_search_show_id`.
        :param str series: series of the episode.
        :param year: year of the series, if any.
        :type year: int
        :param country_code: country code of the series, if any.
        :type country_code: str
        :return: the show id, if found.
        :rtype: int
        """
        show_ids = self._get_show_ids()
        show_id = None

        # attempt with year
        if not show_id and year:
            logger.debug('Getting show id with year')
            show_id = show_ids.get('%s %d' % (series, year))

        # attempt clean
        if not show_id:
            logger.debug('Getting show id')
            show_id = show_ids.get(series)

        # search as last resort
        if not show_id:
            logger.warning('Series not found in show ids')
            show_id = self._search_show_id(series)

        return show_id

    def query(self, series, season, year=None):
        # get the show id
        show_id = self.get_show_id(series, year)
        if show_id is None:
            logger.error('No show id found for %r (%r)', series, year)
            return []

        # get the page of the season of the show
        logger.info('Getting the page of show id %d, season %d', show_id, season)
        r = self.session.get(self.server_url + 'ajax_loadShow.php', params={'show': show_id, 'season': season})
        r.raise_for_status()
        if r.status_code == 304:
            raise TooManyRequests()
        soup = ParserBeautifulSoup(r.content, ['lxml', 'html.parser'])

        subtitles = []
        for table in soup.select('table'):
            link = table.select('tr > td.NewsTitle > a')[0]
            page_link = self.server_url + link.get('href')[22:]
            guess = guessit(link.text)
            series = guess.get('title')
            season = guess.get('season')
            episode = guess.get('episode')
            title = guess.get('episode_title')
            year = guess.get('year')

            for row in table.select('tr'):
                cell = row('td')
                if row.select('td.newsClaro') != []:
                    version = cell[3]
                    version = sanitize_release_group(version)[8:]
                elif row.select('td.language') != []:
                    language = Language.fromtusubtitulo(sanitize(cell[4].text))
                    status = sanitize(cell[5].text)
                    if status != 'completado':
                        logger.debug('Ignoring subtitle with status %s', status)
                        continue
                    download_link = self.server_url + cell[6].a.get('href')[22:]
                    subtitle = TuSubtituloSubtitle(language, page_link, series, season, episode, title, year,
                                                   version, download_link)
                    logger.debug('Found subtitle %r', subtitle)
                    subtitles.append(subtitle)

        return subtitles

    def list_subtitles(self, video, languages):
        return [s for s in self.query(video.series, video.season, video.year)
                if s.language in languages and s.episode == video.episode]

    def download_subtitle(self, subtitle):
        # donwload the subtitle
        logger.info('Downloading subtitle %r', subtitle)
        r = self.session.get(subtitle.download_link, timeout=10)
        r.raise_for_status()

        if not r.content:
            logger.debug('Unable to download subtitle. No data returned from provider')
            return

        subtitle.content = fix_line_ending(r.content)
