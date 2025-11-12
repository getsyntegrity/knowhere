from urllib.parse import unquote, unquote_plus


class UrlDecoder:
    """
    一个用于URL解码的工具类，可以处理包含特殊字符和中文字符的编码字符串。
    它也能稳健地处理不完整或格式错误的编码。
    """

    @staticmethod
    def decode_string(encoded_text: str) -> str:
        """
        对一个URL编码的字符串进行解码。
        它会将 %xx 形式的编码转换为原始字符。
        对于格式不正确的编码（如 '%2'），此函数默认会保留原始字符，不会抛出错误。

        :param encoded_text: 需要解码的URL编码字符串。
        :return: 解码后的原始字符串。
        """
        return unquote(encoded_text, encoding='utf-8')

    @staticmethod
    def decode_string_plus(encoded_text: str) -> str:
        """
        对一个URL编码的字符串进行解码，同时会将 '+' 符号转换为空格。
        这在处理网页表单提交的查询字符串时非常有用。

        :param encoded_text: 需要解码的URL编码字符串。
        :return: 解码后的原始字符串。
        """
        return unquote_plus(encoded_text, encoding='utf-8')