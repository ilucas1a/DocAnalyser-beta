"""
substack_utils.py

Substack transcript scraping utilities for DocAnalyser.
Uses Selenium with automatic browser detection (Chrome, Edge, or Firefox).
Handles Substack's format where timestamps are on separate lines from text.

Usage:
    from substack_utils import is_substack_url, fetch_substack_transcript
"""

import re
from typing import Optional, Tuple, Any, Dict, List
import time
import logging


def is_substack_url(url: str) -> bool:
    """Check if a URL is a Substack post URL."""
    if not url:
        return False
    return 'substack.com' in url.lower()


def extract_post_slug(url: str) -> Optional[str]:
    """Extract the post slug from a Substack URL."""
    if not url:
        return None
    match = re.search(r'/p/([^/?#]+)', url)
    return match.group(1) if match else None


def get_webdriver(headless: bool = True):
    """
    Get a working WebDriver, trying Chrome, Edge, then Firefox.
    
    Args:
        headless: Whether to run in headless mode (invisible)
        
    Returns:
        Tuple of (driver, browser_name) or (None, None) if all fail
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.common.exceptions import WebDriverException
    
    def setup_chrome_options():
        options = ChromeOptions()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        options.add_argument('--log-level=3')
        return options
    
    def setup_edge_options():
        options = EdgeOptions()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--log-level=3')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        return options
    
    def setup_firefox_options():
        options = FirefoxOptions()
        if headless:
            options.add_argument('--headless')
        return options
    
    browsers = [
        ('Chrome', webdriver.Chrome, setup_chrome_options),
        ('Edge', webdriver.Edge, setup_edge_options),
        ('Firefox', webdriver.Firefox, setup_firefox_options),
    ]
    
    for browser_name, driver_class, options_func in browsers:
        try:
            print(f"🔍 Trying {browser_name}...")
            options = options_func()
            driver = driver_class(options=options)
            driver.set_page_load_timeout(30)
            print(f"✅ Using {browser_name}")
            return driver, browser_name
        except WebDriverException as e:
            print(f"⚠️ {browser_name} not available")
            continue
        except Exception as e:
            print(f"⚠️ {browser_name} error: {str(e)[:50]}")
            continue
    
    return None, None


def fetch_substack_transcript(url: str) -> Tuple[bool, Any, str, str, Dict]:
    """
    Fetch transcript from a Substack video post using Selenium.
    
    Opens the page in a headless browser, clicks the transcript button,
    waits for content to load, then scrapes the transcript.
    
    Works with Chrome, Edge, or Firefox - whichever is installed.
    
    Args:
        url: Substack post URL
        
    Returns:
        Tuple of (success, result/error, title, source_type, metadata)
    """
    try:
        # Check if Selenium is available
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
        except ImportError:
            error = "Selenium not installed. Install with: pip install selenium"
            print(f"❌ {error}")
            return False, error, "", "substack", {}
        
        print(f"🌐 Starting browser automation for Substack...")
        
        # Get a working browser
        driver, browser_name = get_webdriver(headless=True)
        
        if not driver:
            error = ("No compatible browser found.\n\n"
                    "Substack transcript scraping requires Chrome, Edge, or Firefox.\n"
                    "Please install one of these browsers.")
            print(f"❌ {error}")
            return False, error, "", "substack", {}
        
        try:
            # Load the page
            print(f"📥 Loading page...")
            driver.get(url)
            time.sleep(2)
            
            # Extract metadata
            try:
                title = driver.title
                if '|' in title:
                    post_title = title.split('|')[0].strip()
                else:
                    post_title = title
                full_title = f"Substack: {post_title}"
            except:
                full_title = "Substack: Unknown Post"
            
            # Extract author
            author = "Unknown"
            try:
                author_elem = driver.find_element(By.CLASS_NAME, "frontend-pencraft-ComponentAuthor")
                author = author_elem.text.strip()
            except:
                pass
            
            # Look for transcript button
            print(f"🔍 Looking for transcript button...")
            transcript_button = None
            
            selectors = [
                (By.XPATH, "//button[contains(translate(text(), 'TRANSCRIPT', 'transcript'), 'transcript')]"),
                (By.XPATH, "//a[contains(translate(text(), 'TRANSCRIPT', 'transcript'), 'transcript')]"),
            ]
            
            for by, selector in selectors:
                try:
                    elements = driver.find_elements(by, selector)
                    for elem in elements:
                        try:
                            if elem.is_displayed() and 'transcript' in elem.text.lower():
                                transcript_button = elem
                                print(f"✅ Found transcript button")
                                break
                        except:
                            continue
                    if transcript_button:
                        break
                except:
                    continue
            
            if transcript_button:
                # Click the transcript button
                print(f"🖱️ Clicking transcript button...")
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", transcript_button)
                    time.sleep(0.5)
                    transcript_button.click()
                    print(f"✅ Clicked, waiting for content...")
                    time.sleep(4)  # Wait for transcript to load
                except Exception as e:
                    print(f"⚠️ Trying JavaScript click...")
                    driver.execute_script("arguments[0].click();", transcript_button)
                    time.sleep(4)
            else:
                print(f"⚠️ No transcript button found")
            
            # Get all text from the page
            page_text = driver.find_element(By.TAG_NAME, "body").text
            
            # Parse transcript
            print(f"📝 Parsing transcript...")
            transcript_entries = parse_transcript_text(page_text)
            
            if not transcript_entries:
                error = ("No transcript found on this Substack page.\n\n"
                        "Possible reasons:\n"
                        "• The video doesn't have a transcript\n"
                        "• The transcript requires authentication\n"
                        "• The transcript format is not recognized")
                print(f"❌ {error}")
                return False, error, "", "substack", {}
            
            # Build metadata
            metadata = {
                'author': author,
                'published_date': '',
                'url': url,
                'post_slug': extract_post_slug(url),
                'entry_count': len(transcript_entries),
                'browser_used': browser_name
            }
            
            print(f"✅ Successfully extracted {len(transcript_entries)} transcript entries")
            
            return True, transcript_entries, full_title, "substack", metadata
            
        finally:
            if driver:
                driver.quit()
                print(f"🚪 Browser closed")
    
    except WebDriverException as e:
        error = f"Browser automation error: {str(e)}"
        print(f"❌ {error}")
        return False, error, "", "substack", {}
    
    except Exception as e:
        error = f"Error: {str(e)}"
        print(f"❌ {error}")
        import traceback
        traceback.print_exc()
        return False, error, "", "substack", {}


def parse_transcript_text(text: str) -> List[Dict]:
    """
    Parse transcript text where timestamps are on separate lines.
    
    Substack format:
        0:00
        Welcome back. We are joined today by...
        0:13
        Hi, Glenn. Thank you very much...
    
    Also handles inline format:
        0:00 Welcome back...
        [0:13] Hi, Glenn...
    """
    entries = []
    lines = text.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Check if this line is JUST a timestamp
        timestamp_only = re.match(r'^(\d{1,2}:\d{2}(?::\d{2})?)$', line)
        
        if timestamp_only:
            timestamp_str = timestamp_only.group(1)
            
            # Get the text from the next line(s)
            text_lines = []
            i += 1
            
            # Collect text until we hit another timestamp or end
            while i < len(lines):
                next_line = lines[i].strip()
                
                # Stop if we hit another timestamp
                if re.match(r'^(\d{1,2}:\d{2}(?::\d{2})?)$', next_line):
                    break
                
                # Add non-empty lines
                if next_line and len(next_line) > 2:
                    text_lines.append(next_line)
                
                i += 1
            
            # Combine text lines
            text_content = ' '.join(text_lines).strip()
            
            # Skip if text is too short
            if len(text_content) < 10:
                continue
            
            # Convert timestamp to seconds
            parts = timestamp_str.split(':')
            try:
                if len(parts) == 2:  # MM:SS
                    seconds = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:  # HH:MM:SS
                    seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                else:
                    i += 1
                    continue
            except (ValueError, IndexError):
                i += 1
                continue
            
            # Add entry
            entries.append({
                'text': text_content,
                'start': seconds,
                'timestamp': timestamp_str
            })
        else:
            # Also check for inline format: "0:00 text" or "[0:13] text"
            inline_match = re.match(r'^\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s+(.+)', line)
            
            if inline_match:
                timestamp_str = inline_match.group(1)
                text_content = inline_match.group(2).strip()
                
                if len(text_content) >= 10:
                    parts = timestamp_str.split(':')
                    try:
                        if len(parts) == 2:
                            seconds = int(parts[0]) * 60 + int(parts[1])
                        elif len(parts) == 3:
                            seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                        else:
                            i += 1
                            continue
                        
                        entries.append({
                            'text': text_content,
                            'start': seconds,
                            'timestamp': timestamp_str
                        })
                    except (ValueError, IndexError):
                        pass
            
            i += 1
    
    return entries


def format_substack_transcript(entries: List[Dict]) -> str:
    """Format transcript entries into readable text."""
    if not entries:
        return ""
    
    lines = []
    for entry in entries:
        timestamp = entry.get('timestamp', '')
        text = entry.get('text', '').strip()
        
        if timestamp:
            lines.append(f"[{timestamp}] {text}")
        else:
            lines.append(text)
    
    return '\n\n'.join(lines)


def check_selenium_available() -> Tuple[bool, str]:
    """Check if Selenium and a compatible browser are available."""
    try:
        from selenium import webdriver
        
        driver, browser_name = get_webdriver(headless=True)
        
        if driver:
            driver.quit()
            return True, f"✅ Selenium ready with {browser_name}"
        else:
            return False, "❌ No compatible browser found"
    
    except ImportError:
        return False, "❌ Selenium not installed"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"


if __name__ == '__main__':
    available, message = check_selenium_available()
    print(message)
