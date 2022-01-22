# eXMB - Bot to mirror r/formula1 highlight clips
# Copyright (C) 2021 - eXhumer

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Bot module to mirror r/formula1 highlight clips"""
from __future__ import annotations
from pathlib import Path
from pkg_resources import require

__version__ = require(__package__)[0].version
__config_path__ = Path.home() / ".config" / __package__
__user_agent__ = f"{__package__}/{__version__}"
__MB = 1 * 1024 * 1024
JUSTSTREAMLIVE_MAX_SIZE = 200 * __MB
MIXTURE_MAX_SIZE = 512 * __MB
REDDIT_MAX_SIZE = 1024 * __MB
STREAMABLE_MAX_SIZE = 250 * __MB
STREAMFF_MAX_SIZE = 200 * __MB
STREAMJA_MAX_SIZE = 30 * __MB
STREAMWO_MAX_SIZE = 512 * __MB
