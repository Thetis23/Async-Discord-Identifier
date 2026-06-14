import os
import sys
import json
import random
import string
import asyncio
import logging
from typing import List, Optional, Set
import aiohttp
from aiohttp_socks import ProxyConnector  # Supports both SOCKS5 and HTTP protocols
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Suppress noisy background logs
logging.basicConfig(level=logging.CRITICAL)

class ProxyManager:
    """Manages proxy loading, rotation, and fault isolation."""
    def __init__(self, filepath: str = "proxy.txt"):
        self.filepath = filepath
        self.proxies: List[str] = []
        self.dead_proxies: Set[str] = set()
        self.load_proxies()

    def load_proxies(self) -> None:
        if not os.path.exists(self.filepath):
            print(f"{Fore.YELLOW}[!] Proxy file '{self.filepath}' not found. Running proxyless mode.")
            return

        with open(self.filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line not in self.proxies:
                    self.proxies.append(line)

        if self.proxies:
            print(f"{Fore.GREEN}[+] Loaded {len(self.proxies)} unique proxies from '{self.filepath}'.")
        else:
            print(f"{Fore.YELLOW}[!] '{self.filepath}' is empty. Running proxyless (Local IP mode).")

    def get_proxy(self) -> Optional[str]:
        active_pool = [p for p in self.proxies if p not in self.dead_proxies]
        if not active_pool and self.proxies:
            print(f"{Fore.YELLOW}[!] All active proxies exhausted. Resetting proxy pool...")
            self.dead_proxies.clear()
            active_pool = self.proxies
        return random.choice(active_pool) if active_pool else None

    def mark_dead(self, proxy: str) -> None:
        if proxy and proxy not in self.dead_proxies:
            self.dead_proxies.add(proxy)
            print(f"{Fore.RED}[-]{Fore.LIGHTBLACK_EX} Proxy flagged dead: {proxy[:25]}...")

class DiscordChecker:
    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager = proxy_manager
        self.config = self.load_config()
        self.webhook_url = self.config.get("webhook_url", "")
        self.concurrency = self.config.get("concurrency_limit", 5)
        self.timeout = self.config.get("timeout_seconds", 10)
        self.max_retries = self.config.get("max_retries", 3)
        self.allowed_chars = string.ascii_lowercase + string.digits + "_."

    def load_config(self) -> dict:
        if not os.path.exists("config.json"):
            default_config = {"webhook_url": "", "concurrency_limit": 5, "timeout_seconds": 10, "max_retries": 3}
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            print(f"{Fore.YELLOW}[!] Default config.json created.")
            return default_config
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)

    def generate_username(self, mode: int) -> str:
        if mode == 2: return "".join(random.choices(self.allowed_chars, k=4))
        elif mode == 3: return "".join(random.choices(string.ascii_lowercase, k=4))
        elif mode == 4: return "".join(random.choices(self.allowed_chars, k=3))
        return ""

    async def send_webhook(self, username: str) -> None:
        if not self.webhook_url or "YOUR_DISCORD_WEBHOOK" in self.webhook_url: return
        payload = {
            "embeds": [{
                "title": "🎉 Username Available!",
                "description": f"The username ` {username} ` is now available.",
                "color": 5763719,
                "footer": {"text": "Async Discord Identifier v1.1"}
            }]
        }
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(self.webhook_url, json=payload, timeout=5)
        except Exception:
            pass

    async def check_username(self, username: str) -> None:
        url = "https://discord.com/api/v9/users/@me/pomelo"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        payload = {"username": username}

        for attempt in range(self.max_retries + 1):
            proxy_str = self.proxy_manager.get_proxy()
            
            connector = None
            if proxy_str:
                proxy_url = f"http://{proxy_str}"
                connector = ProxyConnector.from_url(proxy_url)

            try:
                timeout_config = aiohttp.ClientTimeout(total=self.timeout)
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.post(url, json=payload, headers=headers, timeout=timeout_config) as resp:
                        
                        # Rate Limit Handling
                        if resp.status == 429:
                            data = await resp.json()
                            retry_after = data.get("retry_after", 2.0)
                            print(f"{Fore.YELLOW}[!] Rate Limited! Backing off for {retry_after}s...")
                            await asyncio.sleep(retry_after)
                            continue
                        
                        # Success / Taken Verification
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("taken") is False:
                                print(f"{Fore.GREEN}[+] AVAILABLE: {username}")
                                await self.send_webhook(username)
                                return
                            else:
                                print(f"{Fore.RED}[-] TAKEN: {username}")
                                return

                        if resp.status in [400, 401]:
                            print(f"{Fore.LIGHTBLACK_EX}[-] Request Blocked ({resp.status}): {username}")
                            return

            except Exception as e:
                print(f"{Fore.LIGHTBLACK_EX}[!] Connection Error: {str(e)[:50]}")
                if proxy_str:
                    self.proxy_manager.mark_dead(proxy_str)
                continue

        print(f"{Fore.YELLOW}[?] EXHAUSTED RETRIES: Skipping {username}")

    async def worker(self, queue: asyncio.Queue) -> None:
        while not queue.empty():
            username = await queue.get()
            try:
                await self.check_username(username)
            finally:
                queue.task_done()

    async def start(self) -> None:
        print(Fore.CYAN + "═" * 55)
        print(f"{Fore.CYAN}          ASYNC DISCORD USERNAME IDENTIFIER (v1.1)")
        print(Fore.CYAN + "═" * 55)
        print(f"1. {Fore.WHITE}Load usernames from list.txt")
        print(f"2. {Fore.WHITE}Generate & check random 4-char usernames (a-z, 0-9, _, .)")
        print(f"3. {Fore.WHITE}Generate & check random 4-letter-only usernames (a-z)")
        print(f"4. {Fore.WHITE}Generate & check random 3-char usernames")
        print(Fore.CYAN + "═" * 55)

        try:
            choice = input(f"{Fore.LIGHTBLUE_EX}Select a Mode (1-4): ").strip()
        except KeyboardInterrupt:
            return

        usernames = []
        if choice == "1":
            if not os.path.exists("list.txt"):
                print(f"{Fore.RED}[!] 'list.txt' file not found!")
                return
            with open("list.txt", "r", encoding="utf-8") as f:
                usernames = [line.strip().lower() for line in f if line.strip()]
        elif choice in ["2", "3", "4"]:
            try:
                amount = int(input(f"{Fore.LIGHTBLUE_EX}How many usernames do you want to check? "))
                seen = set()
                while len(seen) < amount:
                    seen.add(self.generate_username(int(choice)))
                usernames = list(seen)
            except ValueError:
                print(f"{Fore.RED}[!] Invalid integer count.")
                return
        else:
            print(f"{Fore.RED}[!] Invalid selection.")
            return

        if not usernames: return

        queue = asyncio.Queue()
        for u in usernames:
            queue.put_nowait(u)

        print(f"\n{Fore.GREEN}[*] Launching session with {self.concurrency} async workers...\n")
        
        tasks = []
        for _ in range(min(self.concurrency, len(usernames))):
            task = asyncio.create_task(self.worker(queue))
            tasks.append(task)
        
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        manager = ProxyManager()
        checker = DiscordChecker(manager)
        asyncio.run(checker.start())
        print(f"\n{Fore.CYAN}[+] Task completed successfully.")
    except KeyboardInterrupt:
        sys.exit(0)
