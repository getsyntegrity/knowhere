from pydantic import BaseModel


class FliesDownload(BaseModel):
    message:str
    file_key: str
    download_url: str
    expires_in_seconds: int