import datetime

def parse_time(time_str):
    unit = time_str[-1]
    amount = int(time_str[:-1])

    if unit == "m":
        return datetime.timedelta(minutes=amount)
    if unit == "h":
        return datetime.timedelta(hours=amount)
    if unit == "d":
        return datetime.timedelta(days=amount)

    return None
