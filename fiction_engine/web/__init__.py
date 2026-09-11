"""
Веб-слой Fiction Engine: Flask-приложение и блупринты.

Файл нужен, чтобы web был обычным пакетом, а не namespace-пакетом.
Namespace-вариант работал для импортов, но ломал упаковку (setuptools
не включал каталог) и заставлял mypy требовать --explicit-package-bases.
"""
