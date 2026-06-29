from datetime import datetime


def format_date(timestamp: float) -> str:
    """Format a timestamp float to a Brazilian Portuguese date string.

    Example:
        format_date(1719100000.0)  # "22/06/2024"
    """
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%d/%m/%Y")



def format_bytes(b: int) -> str:
    """Human-readable byte size with Brazilian decimal separator.

    Example:
        format_bytes(3_400_000_000)  # "3,2 GB"
        format_bytes(1536)           # "1,5 KB"
    """
    if b < 1024:
        return f"{b} B"
    if b < 1024 ** 2:
        return f"{b / 1024:.1f} KB".replace(".", ",")
    if b < 1024 ** 3:
        return f"{b / 1024**2:.1f} MB".replace(".", ",")
    return f"{b / 1024**3:.1f} GB".replace(".", ",")


def format_time(seconds: int) -> str:
    """Human-readable time estimate in Portuguese.

    Example:
        format_time(125)  # "~2 minutos"
        format_time(45)   # "~45 segundos"
    """
    if seconds < 60:
        return f"~{seconds} segundos"
    minutes = seconds // 60
    if minutes == 1:
        return "~1 minuto"
    return f"~{minutes} minutos"
