import os
import re
import json
import logging
import threading
from urllib.parse import urlparse, urljoin
from typing import List, Callable, Optional

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class BilibiliCrawler:
    """专门针对B站专栏/动态的图片爬虫（增强版）"""

    # B站图片CDN的正则（匹配 i0.hdslb.com, i1.hdslb.com 等）
    BILI_CDN_PATTERN = re.compile(r'https?://i\d\.hdslb\.com/[^\s"\']+\.(?:jpg|jpeg|png|gif|webp)', re.I)

    # 通用图片URL正则（匹配常见图片格式）
    GENERAL_IMG_PATTERN = re.compile(r'https?://[^\s"\']+\.(?:jpg|jpeg|png|gif|webp)', re.I)

    def __init__(self, url: str, download_folder: str,
                 callback: Optional[Callable[[int, int, str], None]] = None):
        self.url = url
        self.download_folder = download_folder
        self.callback = callback
        self._stop_event = threading.Event()
        self._session = self._create_session()
        self.image_urls = []

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        return session

    def stop(self):
        self._stop_event.set()

    def fetch_image_urls(self) -> List[str]:
        """提取页面中的图片URL（多策略，全面覆盖）"""
        try:
            response = self._session.get(self.url, timeout=15)
            response.encoding = 'utf-8'
            response.raise_for_status()
            html = response.text
            urls = []

            # ----- 策略1：从 window.__INITIAL_STATE__ 中解析 -----
            match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    # 递归搜索所有字典值中的图片URL
                    urls.extend(self._extract_urls_from_json(data))
                except Exception as e:
                    logger.warning("解析 __INITIAL_STATE__ 失败: %s", e)

            # ----- 策略2：从 __NEXT_DATA__ 中解析 -----
            if not urls:
                match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        urls.extend(self._extract_urls_from_json(data))
                    except Exception as e:
                        logger.warning("解析 __NEXT_DATA__ 失败: %s", e)

            # ----- 策略3：从所有 <script> 标签中提取可能包含的图片URL -----
            soup = BeautifulSoup(html, 'html.parser')
            for script in soup.find_all('script'):
                if script.string:
                    # 从JavaScript字符串中提取图片URL
                    found = self.GENERAL_IMG_PATTERN.findall(script.string)
                    urls.extend(found)

            # ----- 策略4：从所有 <img> 标签及其各种懒加载属性中提取 -----
            for img in soup.find_all('img'):
                # 尝试多种可能的属性
                for attr in ['src', 'data-src', 'data-original', 'data-lazy', 'data-srcset', 'data-actualsrc']:
                    src = img.get(attr)
                    if src:
                        # 处理相对路径
                        full_url = urljoin(self.url, src)
                        if self.GENERAL_IMG_PATTERN.match(full_url):
                            urls.append(full_url)
                            break  # 找到一个就跳出内层循环

            # ----- 策略5：从 <noscript> 标签中提取（有些图片放在noscript里）-----
            for noscript in soup.find_all('noscript'):
                noscript_html = noscript.decode_contents()
                found = self.GENERAL_IMG_PATTERN.findall(noscript_html)
                urls.extend(found)

            # ----- 策略6：从 HTML 文本中直接搜索所有B站CDN图片链接 -----
            urls.extend(self.BILI_CDN_PATTERN.findall(html))

            # ----- 策略7：从 HTML 文本中直接搜索所有可能的图片链接（限制常见域名避免垃圾）-----
            all_img_urls = self.GENERAL_IMG_PATTERN.findall(html)
            for url_candidate in all_img_urls:
                # 只保留可信的图片源
                if any(domain in url_candidate for domain in [
                    '.hdslb.com', '.bilibili.com', 'pixiv.net', 'artstation.com',
                    'deviantart.com', 'pstatic.net', 'akamaized.net'
                ]):
                    urls.append(url_candidate)
                # 也可以无条件添加，但可能会引入非图片链接，这里我们保守一些

            # 去重并过滤掉太短或无效的URL
            self.image_urls = list(set(urls))
            # 再次过滤：确保URL长度合理且包含图片扩展名（可选）
            self.image_urls = [u for u in self.image_urls if len(u) > 10 and re.search(r'\.(jpg|jpeg|png|gif|webp)', u, re.I)]

            logger.info("共找到 %d 张图片", len(self.image_urls))
            return self.image_urls

        except Exception as e:
            logger.exception("B站页面爬取失败: %s", e)
            return []

    def _extract_urls_from_json(self, obj, max_depth=5) -> List[str]:
        """递归从JSON对象中提取所有可能的图片URL"""
        urls = []
        if max_depth <= 0:
            return urls
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and self.GENERAL_IMG_PATTERN.match(value):
                    urls.append(value)
                else:
                    urls.extend(self._extract_urls_from_json(value, max_depth-1))
        elif isinstance(obj, list):
            for item in obj:
                urls.extend(self._extract_urls_from_json(item, max_depth-1))
        return urls

    def download_images(self, selected_indices: List[int], max_workers: int = 5) -> List[str]:
        """下载选中的图片（并发）"""
        if not self.image_urls:
            logger.warning("没有图片URL可下载")
            return []

        if not os.path.exists(self.download_folder):
            os.makedirs(self.download_folder)

        urls_to_download = [self.image_urls[i] for i in selected_indices if i < len(self.image_urls)]
        if not urls_to_download:
            return []

        downloaded = []
        failed = []
        total = len(urls_to_download)

        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(self._download_single, url, idx): (url, idx)
                for idx, url in enumerate(urls_to_download)
            }
            for future in as_completed(future_to_url):
                if self._stop_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                url, idx = future_to_url[future]
                try:
                    filepath = future.result()
                    if filepath:
                        downloaded.append(filepath)
                    else:
                        failed.append(url)
                except Exception as e:
                    logger.error("下载异常 %s: %s", url, e)
                    failed.append(url)

                if self.callback:
                    self.callback(len(downloaded) + len(failed), total, os.path.basename(url))

        logger.info("下载完成: 成功 %d, 失败 %d", len(downloaded), len(failed))
        return downloaded

    def _download_single(self, url: str, index: int) -> Optional[str]:
        """下载单张图片，返回本地路径或None"""
        if self._stop_event.is_set():
            return None
        try:
            # 从URL提取文件名
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path)
            if not filename or '.' not in filename:
                filename = f"bili_image_{index}.jpg"
            # 移除危险字符
            filename = re.sub(r'[\\/*?:"<>|]', '_', filename)

            filepath = os.path.join(self.download_folder, filename)
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(filepath):
                filepath = os.path.join(self.download_folder, f"{base}_{counter}{ext}")
                counter += 1

            # 下载
            response = self._session.get(url, stream=True, timeout=(5, 15))
            response.raise_for_status()
            # 验证内容类型
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                logger.warning("URL %s 不是图片 (Content-Type: %s)", url, content_type)
                return None

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self._stop_event.is_set():
                        f.close()
                        os.remove(filepath)
                        return None
                    f.write(chunk)
            return filepath
        except Exception as e:
            logger.error("下载失败 %s: %s", url, e)
            return None