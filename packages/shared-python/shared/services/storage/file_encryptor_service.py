import os
import pickle

from cryptography.fernet import Fernet


class FernetPickleEncryptor:
    encrypt = False

    def __init__(self, key: bytes = b"nc1BPZSkNb7Oc82_Wo3QoZTmJCEnQtpKZ2n-Z5F4CwY="):
        self.cipher = Fernet(key)

    def save_to_file(self, data: any, file_path: str):
        serialized_data = pickle.dumps(data)  # Serialize the input payload.
        encrypted_data = self.cipher.encrypt(
            serialized_data
        )  # Encrypt the serialized bytes.
        with open(file_path, "wb") as f:
            f.write(encrypted_data)

    def load_from_file(self, file_path: str) -> any:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {file_path} does not exist.")
        with open(file_path, "rb") as f:
            encrypted_data = f.read()
        decrypted_data = self.cipher.decrypt(encrypted_data)  # Decrypt the file bytes.
        loaded_data = pickle.loads(decrypted_data)  # Deserialize the decrypted payload.
        return loaded_data


encryptor = FernetPickleEncryptor()

if __name__ == "__main__":
    # 2. Encrypt the payload.
    data = {"key": "value"}
    # 3. Save the encrypted payload to a file.
    file_path = "data.pkl"
    encryptor.save_to_file(data, file_path)
    print(f"Encrypted data saved to file: {file_path}")

    # 4. Load the encrypted payload back from disk.
    decrypted_data = encryptor.load_from_file(file_path)
    print("Decrypted data loaded from file:", decrypted_data)
