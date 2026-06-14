import os
import sys
import json
import random
import string
import asyncio
import logging
from typing import List, Optional, Set
import aiohttp
from colorama import Fore, Style, init

# Colorama modülünü başlatıyoruz
init(autoreset=True)

# Gereksiz asyncio/aiohttp log kalabalığını gizliyoruz
logging.basicConfig(level=logging.CRITICAL)


class ProxyManager:
    """Proxy yükleme, rastgele döndürme ve hata takibi işlemlerini yönetir."""
    def __init__(self, filepath: str = "proxy.txt"):
        self.filepath = filepath
        self.proxies: List[str] = []
        self.dead_proxies: Set[str] = set()
        self.load_proxies()

    def load_proxies(self) -> None:
        if not os.path.exists(self.filepath):
            print(f"{Fore.YELLOW}[!] Proxy dosyası '{self.filepath}' bulunamadı. Proxysiz çalışılıyor (Önerilmez).")
            return

        with open(self.filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # user:pass@host:port formatını aiohttp'nin anlayacağı http:// biçimine getiriyoruz
                if "@" in line:
                    proxy_url = f"http://{line}"
                    if proxy_url not in self.proxies:
                        self.proxies.append(proxy_url)
                else:
                    # Sadece host:port formatı için yedek plan
                    proxy_url = f"http://{line}"
                    if proxy_url not in self.proxies:
                        self.proxies.append(proxy_url)

        print(f"{Fore.GREEN}[+] {len(self.proxies)} adet benzersiz proxy '{self.filepath}' dosyasından yüklendi.")

    def get_proxy(self) -> Optional[str]:
        """Aktif proxy havuzundan rastgele bir proxy seçer."""
        active_pool = [p for p in self.proxies if p not in self.dead_proxies]
        
        # Eğer tüm proxyler hata aldıysa, hepsine bir şans daha vermek için havuzu sıfırlıyoruz
        if not active_pool and self.proxies:
            print(f"{Fore.YELLOW}[!] Tüm proxyler çalışamaz durumda işaretlendi. Proxy havuzu sıfırlanıyor...")
            self.dead_proxies.clear()
            active_pool = self.proxies

        return random.choice(active_pool) if active_pool else None

    def mark_dead(self, proxy: str) -> None:
        """Hata veren bir proxy'yi kara listeye alır ve tekrar kullanılmasını engeller."""
        if proxy and proxy not in self.dead_proxies:
            self.dead_proxies.add(proxy)
            print(f"{Fore.RED}[-]{Fore.LIGHTBLACK_EX} Proxy devre dışı bırakıldı: {proxy[:30]}...")


class DiscordChecker:
    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager = proxy_manager
        self.config = self.load_config()
        self.webhook_url = self.config.get("webhook_url", "")
        self.concurrency = self.config.get("concurrency_limit", 5)
        self.timeout = self.config.get("timeout_seconds", 10)
        self.max_retries = self.config.get("max_retries", 3)
        
        # Discord'un izin verdiği karakterler: harfler, rakamlar, alt çizgi ve nokta
        self.allowed_chars = string.ascii_lowercase + string.digits + "_."

    def load_config(self) -> dict:
        if not os.path.exists("config.json"):
            # Dosya yoksa varsayılan bir şablon oluşturuyoruz
            default_config = {
                "webhook_url": "",
                "concurrency_limit": 5,
                "timeout_seconds": 10,
                "max_retries": 3
            }
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            print(f"{Fore.YELLOW}[!] Varsayılan config.json oluşturuldu. Lütfen webhook URL'nizi girin.")
            return default_config

        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)

    def generate_username(self, mode: int) -> str:
        """Seçilen moda göre rastgele kullanıcı adı üretir."""
        if mode == 2:  # 4 karakter karışık
            return "".join(random.choices(self.allowed_chars, k=4))
        elif mode == 3:  # Sadece 4 harf
            return "".join(random.choices(string.ascii_lowercase, k=4))
        elif mode == 4:  # 3 karakter karışık
            return "".join(random.choices(self.allowed_chars, k=3))
        return ""

    async def send_webhook(self, session: aiohttp.ClientSession, username: str) -> None:
        """Boştaki kullanıcı adını Discord Webhook kanalınıza gönderir."""
        if not self.webhook_url or "BURAYA_DISCORD_WEBHOOK" in self.webhook_url:
            return

        payload = {
            "embeds": [{
                "title": "🎉 Kullanıcı Adı Alınabilir!",
                "description": f"Şu kullanıcı adı şu an boşta: ` {username} `",
                "color": 5763719,  # Discord Yeşil rengi
                "footer": {"text": "Gelişmiş Discord Checker v1.0"}
            }]
        }
        try:
            async with session.post(self.webhook_url, json=payload, timeout=5) as resp:
                if resp.status not in [200, 204]:
                    print(f"{Fore.YELLOW}[!] Webhook beklenmedik bir hata kodu döndürdü: {resp.status}")
        except Exception:
            print(f"{Fore.RED}[!] Boştaki kullanıcı adı Webhook'a gönderilemedi.")

    async def check_username(self, session: aiohttp.ClientSession, username: str) -> None:
        """Kullanıcı adının durumunu Discord API üzerinden sorgular."""
        url = "https://discord.com/api/v9/users/@me/pomelo"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        payload = {"username": username}

        for attempt in range(self.max_retries + 1):
            proxy = self.proxy_manager.get_proxy()
            
            try:
                timeout_config = aiohttp.ClientTimeout(total=self.timeout)
                async with session.post(url, json=payload, headers=headers, proxy=proxy, timeout=timeout_config) as resp:
                    
                    # 1. Rate Limit (İstek Sınırı) Yönetimi
                    if resp.status == 429:
                        data = await resp.json()
                        retry_after = data.get("retry_after", 2.0)
                        print(f"{Fore.YELLOW}[!] İstek Sınırı! Proxy: {proxy[:25] if proxy else 'Yerel IP'}. {retry_after}s bekleniyor...")
                        await asyncio.sleep(retry_after)
                        continue  # Süre bitince tekrar dene
                    
                    # 2. Başarılı İstek Durumu
                    if resp.status == 200:
                        data = await resp.json()
                        # 'taken' değeri False ise kullanıcı adı boşta demektir.
                        if data.get("taken") is False:
                            print(f"{Fore.GREEN}[+] ALINABİLİR: {username}")
                            await self.send_webhook(session, username)
                            return
                        else:
                            print(f"{Fore.RED}[-] DOLU: {username}")
                            return

                    # 3. Geçersiz İstek veya Engellenme Durumu
                    if resp.status in [400, 401]:
                        print(f"{Fore.LIGHTBLACK_EX}[-] İstek Reddedildi ({resp.status}) sorgulanamıyor: {username}")
                        return

            except (aiohttp.ClientError, asyncio.TimeoutError):
                # Ağ kopması veya yanıt vermeyen proxy durumunda proxy'yi devre dışı bırakıyoruz
                if proxy:
                    self.proxy_manager.mark_dead(proxy)
                continue

        print(f"{Fore.YELLOW}[?] DENEMELER TÜKENDİ: {username} atlanıyor.")

    async def worker(self, queue: asyncio.Queue, session: aiohttp.ClientSession) -> None:
        """Kuyruktaki kullanıcı adlarını sırayla çeken asenkron işçi."""
        while not queue.empty():
            username = await queue.get()
            try:
                await self.check_username(session, username)
            finally:
                queue.task_done()

    async def start(self) -> None:
        # Arayüz Başlığı
        print(Fore.CYAN + "═" * 55)
        print(f"{Fore.CYAN}         DISCORD KULLANICI ADI KONTROL ARACI")
        print(Fore.CYAN + "═" * 55)
        print(f"1. {Fore.WHITE}Kullanıcı adlarını list.txt dosyasından yükle")
        print(f"2. {Fore.WHITE}Rastgele 4 karakterli üret ve kontrol et (a-z, 0-9, _, .)")
        print(f"3. {Fore.WHITE}Rastgele 4 harfli üret ve kontrol et (sadece a-z)")
        print(f"4. {Fore.WHITE}Rastgele 3 karakterli üret ve kontrol et")
        print(Fore.CYAN + "═" * 55)

        try:
            choice = input(f"{Fore.LIGHTBLUE_EX}Bir Mod Seçin (1-4): ").strip()
        except KeyboardInterrupt:
            return

        usernames = []
        if choice == "1":
            if not os.path.exists("list.txt"):
                print(f"{Fore.RED}[!] 'list.txt' dosyası bulunamadı! Lütfen dosyayı oluşturup içine isimleri yazın.")
                return
            with open("list.txt", "r", encoding="utf-8") as f:
                usernames = [line.strip().lower() for line in f if line.strip()]
            print(f"{Fore.GREEN}[+] list.txt dosyasından {len(usernames)} adet isim içeri aktarıldı.")
        elif choice in ["2", "3", "4"]:
            try:
                amount = int(input(f"{Fore.LIGHTBLUE_EX}Kaç adet rastgele kullanıcı adı kontrol edilsin? "))
                mode_num = int(choice)
                
                # Aynı isimlerin tekrar üretilmesini engellemek için küme (set) kullanıyoruz
                seen = set()
                while len(seen) < amount:
                    seen.add(self.generate_username(mode_num))
                usernames = list(seen)
            except ValueError:
                print(f"{Fore.RED}[!] Geçersiz sayı girişi. İşlem iptal edildi.")
                return
        else:
            print(f"{Fore.RED}[!] Geçersiz mod seçimi yapıldı.")
            return

        if not usernames:
            print(f"{Fore.YELLOW}[!] Kontrol edilecek kullanıcı adı bulunamadı. Çıkılıyor.")
            return

        # Asenkron Sıra (Queue) Sistemi
        queue = asyncio.Queue()
        for u in usernames:
            queue.put_nowait(u)

        print(f"\n{Fore.GREEN}[*] {self.concurrency} adet eşzamanlı işçi ile kontrol işlemi başlatılıyor...\n")
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for _ in range(min(self.concurrency, len(usernames))):
                task = asyncio.create_task(self.worker(queue, session))
                tasks.append(task)
            
            await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        manager = ProxyManager()
        checker = DiscordChecker(manager)
        asyncio.run(checker.start())
        print(f"\n{Fore.CYAN}[+] İşlem başarıyla tamamlandı.")
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[!] İşlem kullanıcı tarafından (Ctrl+C) iptal edildi.")
        sys.exit(0)