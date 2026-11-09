# PyMumble 1.6.1 packaging repair

Upstream: https://github.com/azlux/pymumble (Azlux), GPL-3.0.
The original source distribution and its LICENSE are included unchanged.

PyPI source URL:
https://files.pythonhosted.org/packages/5d/45/1cbf709103165317e9455d4648fb16bb9dab5a542ef67efb54c28c7ef139/pymumble-1.6.1.tar.gz
Source SHA-256: c17300413dbf2d754a8b1edf0bb599320bc50bc31b799fc8c91ce1d4ca6774fa

The upstream source distribution omits `requirements.txt`, which `setup.py`
requires. A cold build fails with FileNotFoundError; an existing wheel cache
masks the error. The repair restores that file verbatim from the distribution's
own `pymumble.egg-info/requires.txt`. No PyMumble application code is modified.

Run `python build-wheel.py` in an isolated build environment with pip to rebuild.
The tested wheel is bundled so fresh TAK nodes do not build this broken source
package. The installer checks its SHA-256 before installation:
2fd030d982ef3a2f84d180fe5f5e544087b0a8f82200e2054057d567426bccbe

The original dependencies are retained: opuslib==3.0.1 and protobuf==3.12.2.
The wheel includes the original GPL license. The source archive, packaging
repair recipe, and wheel are maintained together here.
