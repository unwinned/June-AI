import random

def get_random_user_agent():
    chrome_versions = [
        "123.0.0.0", "124.0.0.0", "125.0.0.0", "126.0.0.0",
        "127.0.0.0", "128.0.0.0", "129.0.0.0", "130.0.0.0",
        "131.0.0.0", "132.0.0.0", "133.0.0.0",
    ]
    platforms = [
        ("Windows NT 10.0; Win64; x64", "Windows"),
        ("Macintosh; Intel Mac OS X 10_15_7", "macOS"),
        ("X11; Linux x86_64", "Linux"),
    ]
    platform, os_name = random.choice(platforms)
    chrome_version = random.choice(chrome_versions)
    user_agent = (
        f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_version} Safari/537.36"
    )
    return user_agent, chrome_version

def get_random_viewport():
    resolutions = [
        {"height": 1080},
        {"width": 1366, "height": 768},
        {"width": 1536, "height": 864},
        {"width": 1440, "height": 900},
        {"width": 1280, "height": 720},
    ]
    return random.choice(resolutions)

def get_random_timezone():
    timezones = [
        "America/New_York", "America/Chicago", "America/Los_Angeles",
        "America/Phoenix", "Europe/London", "Europe/Paris", "Europe/Berlin",
        "Asia/Tokyo", "Asia/Singapore", "Australia/Sydney",
    ]
    return random.choice(timezones)
