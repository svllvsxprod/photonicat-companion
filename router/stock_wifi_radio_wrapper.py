"""Installed beside the unmodified pcat_util/wifi_radio.pyc."""
import hashlib as _pc_hashlib
import importlib.util as _pc_importlib
from pathlib import Path as _PcPath

_pc_vendor = _PcPath(__file__).with_suffix('.pyc')
_pc_loader = _pc_importlib.spec_from_file_location(__name__, _pc_vendor).loader
exec(_pc_loader.get_code(__name__), globals())
if _pc_hashlib.sha256(_pc_vendor.read_bytes()).hexdigest() == '89fc829ecb576c359e5abaa164504b3aac107524d70353681aea01b7c127ce0a':
    from wifi_persistence import install as _pc_install_wifi_persistence
    _pc_install_wifi_persistence(globals())
