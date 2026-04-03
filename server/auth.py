import bcrypt

def get_password_hash(password: str) -> str:
  
    # 1. Convert string to bytes
    pwd_bytes = password.encode('utf-8')
    
    # 2. Generate salt and hash
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(pwd_bytes, salt)
    
    # 3. Decode back to string for database storage
    return hashed_bytes.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    
    # 1. Convert inputs to bytes
    pwd_bytes = plain_password.encode('utf-8')
    hash_bytes = hashed_password.encode('utf-8')
    
    # 2. Check using bcrypt
    return bcrypt.checkpw(pwd_bytes, hash_bytes)