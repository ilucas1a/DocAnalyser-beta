"""
google_drive_handler.py - Google Drive API integration for DocAnalyser.

Provides OAuth 2.0 authentication, file listing, downloading, and uploading.
Requires: google-api-python-client, google-auth-oauthlib (pip install both)

Credentials setup:
  Place gdrive_credentials.json in %APPDATA%/DocAnalyser_Beta/
  (Download from Google Cloud Console -> APIs & Services -> Credentials)

Token is saved automatically after first sign-in to:
  %APPDATA%/DocAnalyser_Beta/gdrive_token.json
"""

import os
import logging

# ------------------------------------------------------------------
# Optional dependency guard
# ------------------------------------------------------------------
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
    import httplib2
    import google_auth_httplib2
    import io as _io
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',   # read any Drive file
    'https://www.googleapis.com/auth/drive.file',        # create/write files this app created
]

FOLDER_MIME = 'application/vnd.google-apps.folder'

# Map Google native MIME types -> (export MIME, file extension)
GDRIVE_EXPORT_MAP = {
    'application/vnd.google-apps.document':     ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'),
    'application/vnd.google-apps.spreadsheet':  ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',       '.xlsx'),
    'application/vnd.google-apps.presentation': ('application/vnd.openxmlformats-officedocument.presentationml.presentation', '.pptx'),
}

# MIME types DocAnalyser can process, with display label
SUPPORTED_MIMES = {
    'application/pdf':                  'PDF',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word Doc',
    'application/msword':               'Word Doc',
    'text/plain':                       'Text',
    'text/csv':                         'CSV',
    'audio/mpeg':                       'MP3',
    'audio/mp3':                        'MP3',
    'audio/wav':                        'WAV',
    'audio/x-wav':                      'WAV',
    'audio/x-m4a':                      'M4A',
    'audio/mp4':                        'M4A',
    'video/mp4':                        'MP4',
    'application/vnd.google-apps.document':     'Google Doc',
    'application/vnd.google-apps.spreadsheet':  'Google Sheet',
    'application/vnd.google-apps.presentation': 'Google Slides',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Excel',
}


# ------------------------------------------------------------------
# Main handler class
# ------------------------------------------------------------------

class GoogleDriveHandler:
    """
    Handles all Google Drive API interactions for DocAnalyser.

    Usage:
        handler = GoogleDriveHandler(data_dir)
        success, error = handler.authenticate()
        files = handler.list_files('root')
        ok, dest = handler.download_file(file_id, '/tmp/myfile.pdf')
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.credentials_path = os.path.join(data_dir, 'gdrive_credentials.json')
        self.token_path = os.path.join(data_dir, 'gdrive_token.json')
        self._creds = None
        self._service = None

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """True if Google API packages are installed."""
        return GDRIVE_AVAILABLE

    def has_credentials_file(self) -> bool:
        """True if gdrive_credentials.json exists."""
        return os.path.exists(self.credentials_path)

    def is_authenticated(self) -> bool:
        """True if signed in with a valid, non-expired token."""
        return self._creds is not None and self._creds.valid

    def get_account_email(self) -> str:
        """Return the signed-in user's email address, or None."""
        if not self._service:
            return None
        try:
            about = self._service.about().get(fields='user').execute()
            return about.get('user', {}).get('emailAddress')
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self, force_new: bool = False) -> tuple:
        """
        Authenticate with Google Drive via OAuth 2.0.

        Opens a browser tab on first use; subsequent calls use the saved token.
        Returns (success: bool, error_message: str or None).
        """
        if not GDRIVE_AVAILABLE:
            return False, (
                "Google API packages are not installed.\n\n"
                "Run this command in your terminal:\n"
                "  pip install google-api-python-client google-auth-oauthlib\n\n"
                "Then restart DocAnalyser."
            )

        if not self.has_credentials_file():
            return False, (
                f"Credentials file not found:\n{self.credentials_path}\n\n"
                "Please download your OAuth credentials from Google Cloud Console\n"
                "(APIs & Services -> Credentials -> Download JSON)\n"
                "and save it as  gdrive_credentials.json  in:\n"
                f"{self.data_dir}"
            )

        creds = None

        # 1. Try loading a previously saved token
        if not force_new and os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception as e:
                logging.warning(f"GDrive: could not load saved token: {e}")
                creds = None

        # 2. Refresh if expired but refresh token is present
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logging.warning(f"GDrive: token refresh failed: {e}")
                creds = None  # Force full re-auth

        # 3. Full browser-based auth flow if needed
        if not creds or not creds.valid:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                # run_local_server opens a browser tab and waits for the OAuth callback
                creds = flow.run_local_server(port=0)
            except Exception as e:
                return False, f"Google sign-in failed:\n{e}"

        # 4. Save the token so we don't need to sign in again
        try:
            with open(self.token_path, 'w') as f:
                f.write(creds.to_json())
        except Exception as e:
            logging.warning(f"GDrive: could not save token: {e}")

        self._creds = creds
        # Build an HTTP transport that disables SSL certificate validation.
        # Required when Kaspersky (or similar security software) performs
        # SSL inspection and replaces Google's certificate with its own.
        _http = httplib2.Http(disable_ssl_certificate_validation=True)
        _authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=_http)
        self._service = build('drive', 'v3', http=_authorized_http, cache_discovery=False)
        return True, None

    def sign_out(self):
        """Remove the saved token and clear the authenticated state."""
        self._creds = None
        self._service = None
        if os.path.exists(self.token_path):
            try:
                os.remove(self.token_path)
            except Exception as e:
                logging.warning(f"GDrive: could not delete token: {e}")

    # ------------------------------------------------------------------
    # File listing
    # ------------------------------------------------------------------

    def list_files(self, folder_id: str = 'root') -> list:
        """
        List files and folders inside a Drive folder.
        Returns a list of dicts: {id, name, mimeType, size, modifiedTime}.
        Folders are returned first; files are sorted by name.
        """
        if not self._service:
            return []

        query = f"'{folder_id}' in parents and trashed=false"
        results = []
        page_token = None

        while True:
            try:
                resp = self._service.files().list(
                    q=query,
                    pageSize=200,
                    fields='nextPageToken, files(id, name, mimeType, size, modifiedTime)',
                    orderBy='folder,name',
                    pageToken=page_token
                ).execute()
                results.extend(resp.get('files', []))
                page_token = resp.get('nextPageToken')
                if not page_token:
                    break
            except Exception as e:
                logging.error(f"GDrive list_files error: {e}")
                break

        return results

    def list_shared_with_me(self) -> list:
        """List files shared with the authenticated user (not trashed)."""
        if not self._service:
            return []
        try:
            resp = self._service.files().list(
                q="sharedWithMe=true and trashed=false",
                pageSize=100,
                fields='files(id, name, mimeType, size, modifiedTime)',
                orderBy='name'
            ).execute()
            return resp.get('files', [])
        except Exception as e:
            logging.error(f"GDrive list_shared_with_me error: {e}")
            return []

    def search_files(self, query_text: str) -> list:
        """Full-text search across My Drive."""
        if not self._service:
            return []
        try:
            # Escape single quotes in the search string
            safe = query_text.replace("'", "\\'")
            resp = self._service.files().list(
                q=f"name contains '{safe}' and trashed=false",
                pageSize=50,
                fields='files(id, name, mimeType, size, modifiedTime)',
                orderBy='modifiedTime desc'
            ).execute()
            return resp.get('files', [])
        except Exception as e:
            logging.error(f"GDrive search error: {e}")
            return []

    def get_file_metadata(self, file_id: str) -> dict:
        """Return metadata dict for a single file, or None on error."""
        if not self._service:
            return None
        try:
            return self._service.files().get(
                fileId=file_id,
                fields='id, name, mimeType, size, modifiedTime, parents, webViewLink'
            ).execute()
        except Exception as e:
            logging.error(f"GDrive get_file_metadata error: {e}")
            return None

    # ------------------------------------------------------------------
    # Downloading
    # ------------------------------------------------------------------

    def download_file(self, file_id: str, dest_path: str,
                      progress_callback=None, mime_type: str = None) -> tuple:
        """
        Download a file to dest_path.
        Google Docs/Sheets/Slides are automatically exported to DOCX/XLSX/PPTX.

        Uses requests with verify=False to bypass Kaspersky SSL inspection,
        which intercepts googleapis.com download traffic and breaks the
        standard MediaIoBaseDownload transport.

        mime_type: if provided, skips the get_file_metadata() API call.
        progress_callback(pct: int) is called with 0-100 during download.

        Returns:
            (True,  actual_dest_path)   on success
            (False, error_message)      on failure
        """
        if not self._creds:
            return False, "Not signed in to Google Drive."

        try:
            import requests
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            if mime_type:
                mime = mime_type
            else:
                meta = self.get_file_metadata(file_id)
                if not meta:
                    return False, "Could not retrieve file information from Google Drive."
                mime = meta.get('mimeType', '')

            # Google native format -> export to office format
            if mime in GDRIVE_EXPORT_MAP:
                export_mime, ext = GDRIVE_EXPORT_MAP[mime]
                base = os.path.splitext(dest_path)[0]
                dest_path = base + ext
                url = (
                    f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
                    f"?mimeType={export_mime}"
                )
            else:
                url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

            # Refresh token if needed before using it
            if self._creds.expired and self._creds.refresh_token:
                from google.auth.transport.requests import Request as _Req
                self._creds.refresh(_Req())

            headers = {'Authorization': f'Bearer {self._creds.token}'}
            response = requests.get(url, headers=headers, verify=False, stream=True)
            response.raise_for_status()

            total = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            with open(dest_path, 'wb') as fh:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total:
                            progress_callback(int(downloaded / total * 100))

            return True, dest_path

        except Exception as e:
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
            return False, str(e)

    # ------------------------------------------------------------------
    # Uploading
    # ------------------------------------------------------------------

    def upload_file(self, local_path: str, drive_name: str = None,
                    folder_id: str = 'root', mime_type: str = None) -> tuple:
        """
        Upload a local file to Google Drive.

        Returns:
            (True,  file_id,    None)          on success
            (False, None,       error_message) on failure
        """
        if not self._service:
            return False, None, "Not signed in to Google Drive."

        if not os.path.exists(local_path):
            return False, None, f"File not found: {local_path}"

        name = drive_name or os.path.basename(local_path)
        file_metadata = {'name': name, 'parents': [folder_id]}
        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)

        try:
            uploaded = self._service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()
            return True, uploaded.get('id'), None
        except Exception as e:
            return False, None, str(e)

    def get_file_web_link(self, file_id: str) -> str:
        """Return the Google Drive web view URL for a file, or None."""
        if not self._service:
            return None
        try:
            f = self._service.files().get(fileId=file_id, fields='webViewLink').execute()
            return f.get('webViewLink')
        except Exception:
            return None

    def create_folder(self, name: str, parent_id: str = 'root') -> str:
        """Create a folder in Google Drive. Returns the new folder's ID, or None."""
        if not self._service:
            return None
        try:
            meta = {
                'name': name,
                'mimeType': FOLDER_MIME,
                'parents': [parent_id]
            }
            folder = self._service.files().create(body=meta, fields='id').execute()
            return folder.get('id')
        except Exception as e:
            logging.error(f"GDrive create_folder error: {e}")
            return None


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------
# Instantiated lazily on first use via get_gdrive_handler()

_handler_instance: GoogleDriveHandler = None


def get_gdrive_handler(data_dir: str = None) -> GoogleDriveHandler:
    """
    Return the shared GoogleDriveHandler instance, creating it if needed.
    Pass data_dir on the first call; subsequent calls can omit it.
    """
    global _handler_instance
    if _handler_instance is None:
        if data_dir is None:
            from config import DATA_DIR
            data_dir = DATA_DIR
        _handler_instance = GoogleDriveHandler(data_dir)
    return _handler_instance
