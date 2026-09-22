"""管理员密钥：只保存 PBKDF2 哈希，不保存明文。"""
import base64, hashlib, hmac, json, os
from pathlib import Path
def create_key_record(secret: str) -> dict:
    if len(secret) < 8: raise ValueError("管理员密钥至少需要 8 个字符")
    salt=os.urandom(32)
    return {"algorithm":"pbkdf2_sha256","iterations":600000,"salt":base64.b64encode(salt).decode(),"hash":base64.b64encode(hashlib.pbkdf2_hmac("sha256",secret.encode(),salt,600000)).decode()}
def verify_key(secret: str, record: dict) -> bool:
    try:
        salt=base64.b64decode(record["salt"],validate=True); expected=base64.b64decode(record["hash"],validate=True)
        actual=hashlib.pbkdf2_hmac("sha256",secret.encode(),salt,int(record["iterations"]))
        return record["algorithm"]=="pbkdf2_sha256" and hmac.compare_digest(actual,expected)
    except (KeyError,TypeError,ValueError): return False
def load_key_record(path: Path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError,OSError,json.JSONDecodeError): return None
def save_key_record(path: Path,record: dict):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
