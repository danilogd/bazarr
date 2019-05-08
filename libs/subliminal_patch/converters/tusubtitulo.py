# -*- coding: utf-8 -*-
from babelfish import LanguageReverseConverter, language_converters


class TuSubtituloConverter(LanguageReverseConverter):
    def __init__(self):
        self.alpha2_converter = language_converters['alpha2']
        self.from_tusubtitulo = {u'Català': ('cat',), 'Galego': ('glg',), 'English': ('eng',),
                                  u'Español (Latinoamérica)': ('ltm',), u'Español (España)': ('spa',)}
        self.to_tusubtitulo = {('cat',): 'Català', ('glg',): 'Galego', ('eng',): 'English',
                                ('ltm',): 'Español (Latinoamérica)', ('spa',): 'Español (España)'}
        self.codes = self.alpha2_converter.codes | set(self.from_tusubtitulo.keys())

    def convert(self, alpha3, country=None, script=None):
        if (alpha3, country) in self.to_tusubtitulo:
            return self.to_tusubtitulo[(alpha3, country)]
        if (alpha3,) in self.to_tusubtitulo:
            return self.to_tusubtitulo[(alpha3,)]

        return self.alpha2_converter.convert(alpha3, country, script)

    def reverse(self, tusubtitulo):
        if tusubtitulo in self.from_tusubtitulo:
            return self.from_tusubtitulo[tusubtitulo]

        return self.alpha2_converter.reverse(tusubtitulo)
