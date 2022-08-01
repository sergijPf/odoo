import re
import unicodedata


def normalize_zip(zip_code: str) -> str:
    return re.sub(r'\D', '', zip_code)


def pl_zip(zip_code: str) -> str:
    _z = normalize_zip(zip_code)
    return f'{_z[:2]}-{_z[2:5]}'


def slugify(value: any, allow_unicode: bool = False) -> str:
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower()).strip()
    return re.sub(r'[-\s]+', '-', value)

