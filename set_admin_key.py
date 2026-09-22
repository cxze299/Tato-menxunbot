from getpass import getpass
from pathlib import Path
from admin_key import create_key_record,save_key_record
p=Path(__file__).resolve().parent/"data"/"admin-key.json"; a=getpass("管理员密钥（至少8个字符）："); b=getpass("再次输入：")
if a!=b: raise SystemExit("两次输入不一致")
save_key_record(p,create_key_record(a)); print(f"已保存哈希：{p}")
