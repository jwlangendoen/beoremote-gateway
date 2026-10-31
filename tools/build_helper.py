"""Build a credential-free TV helper; signing material stays in .local."""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def source_hash():
    digest=hashlib.sha256()
    for path in sorted((ROOT/'tv_helper').rglob('*')):
        if path.is_file() and ('src' in path.parts or path.suffix=='.xml'):
            digest.update(path.relative_to(ROOT).as_posix().encode()+b'\0'+path.read_bytes())
    return digest.hexdigest()


def build():
    sdk_tools=Path(os.environ.get('BEOR_ANDROID_TOOLS', ROOT.parent/'android-spotify-client/.tools'))
    jdk=sdk_tools/'jdk/Contents/Home'
    sdk=sdk_tools/'sdk'
    bt=sdk/'build-tools/36.1.0'
    android=sdk/'platforms/android-28/android.jar'
    target=ROOT/'.local/helper-build'
    shutil.rmtree(target,ignore_errors=True)
    (target/'classes').mkdir(parents=True)
    (target/'generated').mkdir()
    def run(*args,env=None):
        result=subprocess.run([str(a)for a in args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env)
        if result.returncode:raise RuntimeError(result.stdout.decode(errors='replace')[:4000])
        return result.stdout
    run(bt/'aapt2','compile','--dir',ROOT/'tv_helper/res','-o',target/'resources.zip')
    run(bt/'aapt2','link','-o',target/'resources.apk','-I',android,'--manifest',ROOT/'tv_helper/AndroidManifest.xml','--java',target/'generated',target/'resources.zip')
    java=sorted((ROOT/'tv_helper/src').rglob('*.java'))+sorted((target/'generated').rglob('*.java'))
    run(jdk/'bin/javac','--release','8','-g:none','-classpath',android,'-d',target/'classes',*java)
    run(jdk/'bin/jar','cf',target/'classes.jar','-C',target/'classes','.')
    run(jdk/'bin/java','-cp',bt/'lib/d8.jar','com.android.tools.r8.D8','--min-api','21','--lib',android,'--output',target,target/'classes.jar')
    import zipfile
    shutil.copyfile(target/'resources.apk',target/'unsigned.apk')
    with zipfile.ZipFile(target/'unsigned.apk','a',compression=zipfile.ZIP_DEFLATED)as z:z.write(target/'classes.dex','classes.dex')
    run(bt/'zipalign','-f','4',target/'unsigned.apk',target/'aligned.apk')
    private=ROOT/'.local/helper-signing.json'
    os.umask(0o077)
    if private.exists():config=json.loads(private.read_text())
    else:
        config={'password':secrets.token_hex(32)}
        private.write_text(json.dumps(config));private.chmod(0o600)
    env={**os.environ,'BEOR_SIGN_PASSWORD':config['password']}
    store=ROOT/'.local/helper-signing.p12'
    if not store.exists():run(jdk/'bin/keytool','-genkeypair','-noprompt','-keystore',store,'-storetype','PKCS12','-alias','beoremote-support','-keyalg','RSA','-keysize','3072','-validity','10000','-dname','CN=Beoremote TV Support','-storepass:env','BEOR_SIGN_PASSWORD','-keypass:env','BEOR_SIGN_PASSWORD',env=env)
    run(jdk/'bin/java','-jar',bt/'lib/apksigner.jar','sign','--ks',store,'--ks-key-alias','beoremote-support','--ks-pass','env:BEOR_SIGN_PASSWORD','--key-pass','env:BEOR_SIGN_PASSWORD','--out',target/'support.apk',target/'aligned.apk',env=env)
    run(jdk/'bin/java','-jar',bt/'lib/apksigner.jar','verify','--verbose',target/'support.apk')
    certificate=run(jdk/'bin/keytool','-exportcert','-keystore',store,'-alias','beoremote-support','-storepass:env','BEOR_SIGN_PASSWORD',env=env)
    raw=(target/'support.apk').read_bytes()
    assets=ROOT/'beoremote_gateway/gateway'
    (assets/'helper_apk.b64').write_text(base64.b64encode(raw).decode()+'\n')
    (assets/'helper_apk.json').write_text(json.dumps({'package':'nl.beoremote.tvhelper','version':'0.1.5','version_code':6,'sha256':hashlib.sha256(raw).hexdigest(),'certificate_sha256':hashlib.sha256(certificate).hexdigest(),'source_sha256':source_hash()},indent=2)+'\n')
    print('Built and verified TV Support 0.1.5; no household data or endpoint in APK.')

if __name__=='__main__':build()
