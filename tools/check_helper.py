"""Verify the credential-free, signed helper artifact against its reviewed source."""
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile
from build_helper import ROOT, source_hash


def check():
    assets=ROOT/'beoremote_gateway/gateway'
    meta=json.loads((assets/'helper_apk.json').read_text())
    raw=base64.b64decode((assets/'helper_apk.b64').read_text().strip(),validate=True)
    assert len(raw)<512*1024
    assert hashlib.sha256(raw).hexdigest()==meta['sha256']
    assert source_hash()==meta['source_sha256'], 'Helper source changed; rebuild the signed artifact.'
    assert meta['package']=='nl.beoremote.tvhelper'
    with zipfile.ZipFile(io.BytesIO(raw)) as apk:
        assert {'AndroidManifest.xml','classes.dex'} <= set(apk.namelist())
        assert apk.read('classes.dex').startswith(b'dex\n')
        assert any(name.startswith('META-INF/') and name.endswith('.RSA') for name in apk.namelist())
    manifest=(ROOT/'tv_helper/AndroidManifest.xml').read_text()
    assert '<activity' not in manifest and 'android:debuggable="false"' in manifest
    assert 'android.permission.DUMP' in manifest and 'android.permission.DEVICE_POWER' in manifest
    print('TV helper artifact, source digest and restricted manifest verified.')

if __name__=='__main__':check()
