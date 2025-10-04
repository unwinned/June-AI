from utils.router import Router
import sys
import asyncio
import time
import colorama
import pyfiglet
from termcolor import colored
from colorama import Fore


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
def run():
    colorama.init()
    rkkt1 = pyfiglet.figlet_format("unwinned.")
    print(Fore.CYAN + rkkt1)
    time.sleep(2)
    soft = "June AI"
    v = f"Current version: v2"
    c = colored(text=v, color="red", attrs=["bold"])
    colored_soft = colored(text=soft, color="red", attrs=["bold"])
    
    madeby = "Made by: https://t.me/just_unwinned"
    colored_madeby = colored(text=madeby, color="red", attrs=["bold"])
    
    print(colored_soft)
    print(colored_madeby)
    print(c + "\n")
    router = Router(__file__)
    router.route()

run()
