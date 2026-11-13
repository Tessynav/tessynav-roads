import json,sys,base64,gzip,hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
src,pw,out=sys.argv[1],sys.argv[2],sys.argv[3]
e=json.load(open(src));b=lambda s:base64.b64decode(s)
key=hashlib.pbkdf2_hmac('sha256',pw.encode(),b(e['salt']),e.get('iter',200000),32)
d=AESGCM(key).decrypt(b(e['iv']),b(e['data']),None)
if e.get('gz'): d=gzip.decompress(d)
open(out,'wb').write(d);print('ok',len(d))
