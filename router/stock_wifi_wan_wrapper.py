"""Installed beside the unmodified pcat_util/wifi_wan.pyc."""
import hashlib as _pc_hashlib
import importlib.util as _pc_importlib
from pathlib import Path as _PcPath

_pc_vendor = _PcPath(__file__).with_suffix('.pyc')
_pc_loader = _pc_importlib.spec_from_file_location(__name__, _pc_vendor).loader
exec(_pc_loader.get_code(__name__), globals())
if _pc_hashlib.sha256(_pc_vendor.read_bytes()).hexdigest() == '1beca22b86bfc7409c34e3826fc5c2ba46bc1673848b8a3c4e1d7b2d960b55b2':
    from wifi_persistence import install_wan as _pc_install_wifi_persistence
    _pc_install_wifi_persistence(globals())
