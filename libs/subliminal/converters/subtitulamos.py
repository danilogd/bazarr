# -*- coding: utf-8 -*-
from babelfish import LanguageReverseConverter, language_converters


class SubtitulamosConverter(LanguageReverseConverter):
    def __init__(self):
        self.alpha2_converter = language_converters['alpha2']
        self.from_subtitulamos = {u'Català': ('cat',), 'Galego': ('glg',), 'English': ('eng',),
                                  u'Español (Latinoamérica)': ('lat',), u'Español (España)': ('spa',)}
        self.to_subtitulamos = {('cat',): 'Català', ('glg',): 'Galego', ('eng',): 'English',
                                ('lat',): 'Español (Latinoamérica)', ('spa',): 'Español (España)'}
        self.codes = self.alpha2_converter.codes | set(self.from_subtitulamos.keys())

    def convert(self, alpha3, country=None, script=None):
        if (alpha3, country) in self.to_subtitulamos:
            return self.to_subtitulamos[(alpha3, country)]
        if (alpha3,) in self.to_subtitulamos:
            return self.to_subtitulamos[(alpha3,)]

        return self.alpha2_converter.convert(alpha3, country, script)

    def reverse(self, subtitulamos):
        if subtitulamos in self.from_subtitulamos:
            return self.from_subtitulamos[subtitulamos]

        return self.alpha2_converter.reverse(subtitulamos)
