"""Installed as pcat_manager_web.py beside the untouched vendor .pyc."""
import importlib.util as _pc_importlib
import hashlib as _pc_hashlib
from pathlib import Path as _PcPath

_pc_vendor = _PcPath(__file__).with_suffix('.pyc')
_pc_loader = _pc_importlib.spec_from_file_location(__name__, _pc_vendor).loader
exec(_pc_loader.get_code(__name__), globals())
from photonicat_radio import install as _pc_install_radio
# A firmware upgrade must not apply this compatibility patch to unknown code.
if _pc_hashlib.sha256(_pc_vendor.read_bytes()).hexdigest() == 'a0daa63fdfe49f80cdcf25bd8e37208c3e67d5ede776afae086c33652a792ea2':
    _pc_install_radio(globals())
