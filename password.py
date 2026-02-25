import os
import json
import hashlib
from typing import Optional

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "data")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

def get_password_hash() -> Optional[str]:
    """从配置文件中读取密码哈希，若无则返回 None"""
    if not os.path.exists(CONFIG_FILE):
        return None
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    return config.get('private_password_hash')

def set_password(password: str):
    """设置新密码（会覆盖旧密码）"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    hash_obj = hashlib.sha256(password.encode())
    password_hash = hash_obj.hexdigest()
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
    config['private_password_hash'] = password_hash
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def verify_password(password: str) -> bool:
    """验证密码是否正确"""
    stored_hash = get_password_hash()
    if stored_hash is None:
        return False
    hash_obj = hashlib.sha256(password.encode())
    return hash_obj.hexdigest() == stored_hash