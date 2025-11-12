import os
import pickle

from cryptography.fernet import Fernet


class FernetPickleEncryptor:
    encrypt = False
    def __init__(self, key: bytes = b'nc1BPZSkNb7Oc82_Wo3QoZTmJCEnQtpKZ2n-Z5F4CwY='):
        self.cipher = Fernet(key)

    def save_to_file(self, data: any, file_path: str):
        serialized_data = pickle.dumps(data)  # 序列化数据
        encrypted_data = self.cipher.encrypt(serialized_data)  # 加密数据
        with open(file_path, 'wb') as f:
            f.write(encrypted_data)

    def load_from_file(self, file_path: str) -> any:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件 {file_path} 不存在。")
        with open(file_path, 'rb') as f:
            encrypted_data = f.read()
        decrypted_data = self.cipher.decrypt(encrypted_data)  # 解密数据
        loaded_data = pickle.loads(decrypted_data)  # 反序列化数据
        return loaded_data

encryptor = FernetPickleEncryptor()

if __name__ == "__main__":
    # 2. 加密数据
    data = {'key': 'value'}
    # 3. 保存加密数据到文件
    file_path = 'data.pkl'
    encryptor.save_to_file(data, file_path)
    print(f"加密数据已保存到文件: {file_path}")

    # 4. 从文件加载加密数据
    decrypted_data = encryptor.load_from_file(file_path)
    print("从文件加载的解密后数据:", decrypted_data)

