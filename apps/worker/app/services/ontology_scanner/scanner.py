"""
Scanner Ontology Module
Scans local filesystem to discover user knowledge assets and build a structured ontology.
Only reads metadata (path, size, mtime) — never reads file content.
"""
import os
import re
import json
import math
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set, Tuple

from loguru import logger


# ==================== Constants ====================

TARGET_EXTENSIONS: Set[str] = {
    "pdf", "docx", "xlsx", "jpg", "jpeg", "png",
    "pptx", "csv", "md", "json", "txt", "xls", "ppt",
}

TYPE_GROUPS: Dict[str, str] = {
    "pdf": "document",
    "docx": "document",
    "doc": "document",
    "md": "document",
    "txt": "document",
    "pptx": "presentation",
    "ppt": "presentation",
    "xlsx": "spreadsheet",
    "xls": "spreadsheet",
    "csv": "spreadsheet",
    "jpg": "image",
    "jpeg": "image",
    "png": "image",
    "json": "structured_data",
}

DEFAULT_SCAN_ROOTS: List[str] = [
    "~/Documents",
    "~/Desktop",
    "~/Downloads",
    "~/Library/CloudStorage",                              # OneDrive / Google Drive / Dropbox
    "~/Library/Mobile Documents/com~apple~CloudDocs",      # iCloud Drive
]

# Directories to always skip (case-insensitive basenames)
BLACKLIST_DIRS: Set[str] = {
    # System
    "library", ".trash", ".spotlight-v100", ".fseventsd",
    ".temporaryitems", ".documentrevisions-v100",
    # Dev tooling
    "node_modules", "__pycache__", ".git", ".svn", ".hg",
    "venv", ".venv", "env", ".env", ".tox", ".nox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "build", "dist", ".egg-info", ".eggs",
    "target",  # Rust/Java
    # IDE
    ".idea", ".vscode", ".vs",
    # macOS app bundles
    ".app", ".framework", ".bundle", ".plugin", ".kext",
    # Package managers
    ".cocoapods", ".gradle", "pods",
    # Cache / temp
    ".cache", ".tmp", "tmp", "temp",
    # Cloud sync noise
    ".dropbox", ".dropbox.cache",
}

# Files whose presence marks a directory as a code/engineering project root
CODE_PROJECT_MARKERS: Set[str] = {
    # Package managers
    "package.json", "requirements.txt", "pipfile", "pyproject.toml",
    "setup.py", "setup.cfg", "cargo.toml", "go.mod", "pom.xml",
    "build.gradle", "gemfile", "composer.json", "mix.exs",
    # Build / config
    "makefile", "cmakelists.txt", "dockerfile",
    "docker-compose.yml", "docker-compose.yaml",
    # VCS
    ".gitignore",
    # IDE / linting
    "tsconfig.json", ".eslintrc", ".eslintrc.js", ".eslintrc.json",
    ".prettierrc", "tox.ini", ".flake8",
    # Lock files
    "package-lock.json", "yarn.lock", "poetry.lock", "pipfile.lock",
}

# Subdirectory names that signal a code/engineering project root
CODE_PROJECT_DIRS: Set[str] = {
    ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache",
    "node_modules", ".git", ".svn", ".hg",
    "venv", ".venv", ".tox", ".nox",
    "build", "dist", ".eggs", ".egg-info",
    "target",  # Rust/Java
    ".idea", ".vscode",
}

# Regex patterns for directory names to skip
BLACKLIST_PATTERNS: List[re.Pattern] = [
    re.compile(r"^\.", re.IGNORECASE),          # Hidden directories (.*) 
    re.compile(r".*\.app$", re.IGNORECASE),     # macOS app bundles
    re.compile(r".*\.framework$", re.IGNORECASE),
    re.compile(r".*\.xcodeproj$", re.IGNORECASE),
    re.compile(r".*\.xcworkspace$", re.IGNORECASE),
]

# Minimum file size to consider (skip 0-byte placeholder files)
MIN_FILE_SIZE: int = 1  # bytes


# ==================== SQLite Schema ====================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS folder_nodes (
    path        TEXT PRIMARY KEY,
    parent      TEXT,
    depth       INTEGER,
    file_count  INTEGER DEFAULT 0,
    total_size  INTEGER DEFAULT 0,
    doc_count   INTEGER DEFAULT 0,
    sheet_count INTEGER DEFAULT 0,
    image_count INTEGER DEFAULT 0,
    data_count  INTEGER DEFAULT 0,
    pres_count  INTEGER DEFAULT 0,
    is_code_project INTEGER DEFAULT 0,
    latest_mtime TEXT,
    score       REAL DEFAULT 0.0,
    scan_time   TEXT
);

CREATE TABLE IF NOT EXISTS file_assets (
    path        TEXT PRIMARY KEY,
    folder      TEXT,
    name        TEXT,
    ext         TEXT,
    type_group  TEXT,
    size        INTEGER,
    mtime       TEXT,
    content_hash TEXT,
    scan_time   TEXT
);

CREATE TABLE IF NOT EXISTS scan_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


# ==================== FileSystemScanner ====================

class FileSystemScanner:
    """
    Scans local directories to discover user knowledge files and build
    a structured ontology stored in SQLite.
    """

    def __init__(
        self,
        scan_roots: List[str] = None,
        db_path: str = "./data/ontology.db",
        blacklist_extra: Set[str] = None,
    ):
        """
        Args:
            scan_roots: List of root directories to scan (supports ~ expansion)
            db_path: Path to the SQLite ontology database
            blacklist_extra: Additional directory names to skip
        """
        self.scan_roots = [
            os.path.expanduser(r) for r in (scan_roots or DEFAULT_SCAN_ROOTS)
        ]
        self.db_path = os.path.expanduser(db_path)
        self.blacklist_dirs = BLACKLIST_DIRS | (blacklist_extra or set())
        self.scan_time = datetime.now().isoformat(timespec="seconds")

        # Ensure DB directory exists
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        # Initialize DB
        self._init_db()

    def _init_db(self):
        """Create SQLite tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a new SQLite connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ==================== Filtering ====================

    def _should_skip(self, dir_path: str, dir_name: str) -> bool:
        """
        Three-level filter to determine if a directory should be skipped.

        Level 1: Blacklist — exact name match (case-insensitive)
        Level 2: Pattern — regex match on directory name
        Level 3: Structural — macOS bundle internals, symlinks
        """
        name_lower = dir_name.lower()

        # Level 1: Blacklist name match
        if name_lower in self.blacklist_dirs:
            return True

        # Level 2: Pattern match
        for pattern in BLACKLIST_PATTERNS:
            if pattern.match(dir_name):
                return True

        # Level 3: Structural checks
        # Skip symlinks to avoid infinite loops
        if os.path.islink(dir_path):
            return True

        # Skip macOS app bundle Contents
        if "Contents" in dir_path and any(
            p.endswith(".app") for p in Path(dir_path).parents
        ):
            return True

        return False

    # ==================== Code Project Detection ====================

    def _is_code_project_root(
        self, filenames: List[str], dirnames: List[str]
    ) -> bool:
        """Check if directory contains code project marker files or dirs."""
        # Check marker files
        filenames_lower = {f.lower() for f in filenames}
        if filenames_lower & CODE_PROJECT_MARKERS:
            return True
        # Check marker subdirectories
        dirnames_lower = {d.lower() for d in dirnames}
        if dirnames_lower & CODE_PROJECT_DIRS:
            return True
        return False

    def _is_inside_code_project(
        self, dirpath: str, known_roots: Set[str]
    ) -> bool:
        """Check if dirpath is inside (or is) a known code project root."""
        for root in known_roots:
            if dirpath == root or dirpath.startswith(root + os.sep):
                return True
        return False

    def _promote_code_parents(self, conn: sqlite3.Connection):
        """
        Bottom-up promotion: if ALL recorded children of a non-code folder
        are code projects, promote the parent to code project too.
        Iterates until no more promotions occur.
        """
        total_promoted = 0
        while True:
            # Find non-code folders whose ALL children (in folder_nodes) are code
            candidates = conn.execute("""
                SELECT DISTINCT parent.path
                FROM folder_nodes parent
                WHERE parent.is_code_project = 0
                  AND EXISTS (
                    SELECT 1 FROM folder_nodes child
                    WHERE child.parent = parent.path
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM folder_nodes child
                    WHERE child.parent = parent.path
                      AND child.is_code_project = 0
                  )
            """).fetchall()

            if not candidates:
                break

            paths = [r["path"] for r in candidates]
            conn.executemany(
                "UPDATE folder_nodes SET is_code_project = 1 WHERE path = ?",
                [(p,) for p in paths]
            )
            conn.commit()
            total_promoted += len(paths)

        if total_promoted:
            logger.info(
                f"🔄 Bottom-up promotion: {total_promoted} folders "
                f"promoted to code project"
            )

    # ==================== Scanning ====================

    def scan(self) -> Dict[str, Any]:
        """
        Main scan entry point. Walks all scan roots and populates the SQLite DB.

        Returns:
            Summary dict with scan statistics.
        """
        logger.info(f"🔍 Starting filesystem scan at {self.scan_time}")
        logger.info(f"📂 Scan roots: {self.scan_roots}")

        conn = self._get_conn()

        # Clear previous scan data
        conn.execute("DELETE FROM folder_nodes")
        conn.execute("DELETE FROM file_assets")
        conn.commit()

        total_folders = 0
        total_files = 0
        skipped_dirs = 0

        # Track which directories are code project roots
        # key: dir path, value: True if code project root detected
        code_project_roots: Set[str] = set()

        for root in self.scan_roots:
            if not os.path.isdir(root):
                logger.warning(f"⚠️ Scan root not found, skipping: {root}")
                continue

            # Check if we can actually read the directory (macOS TCC protection)
            try:
                os.listdir(root)
            except PermissionError:
                logger.warning(
                    f"🔒 Permission denied: {root} — "
                    f"grant Full Disk Access in System Settings → "
                    f"Privacy & Security for your terminal/IDE"
                )
                continue

            for dirpath, dirnames, filenames in os.walk(root, topdown=True):
                # Detect code project root markers BEFORE filtering
                # (so .git, .pytest_cache etc are still visible)
                if self._is_code_project_root(filenames, dirnames):
                    code_project_roots.add(dirpath)

                # Filter dirnames in-place to prevent os.walk from descending
                original_count = len(dirnames)
                dirnames[:] = [
                    d for d in dirnames
                    if not self._should_skip(os.path.join(dirpath, d), d)
                ]
                skipped_dirs += original_count - len(dirnames)

                # Determine if current dir is inside a code project
                is_code = self._is_inside_code_project(
                    dirpath, code_project_roots
                )

                # Collect target files in this directory
                target_files = self._collect_target_files(dirpath, filenames)

                if not target_files:
                    continue  # Skip folders with no target files

                # Compute folder stats
                folder_node = self._build_folder_node(
                    dirpath, root, target_files, is_code
                )
                total_folders += 1
                total_files += len(target_files)

                # Insert into DB
                self._insert_folder_node(conn, folder_node)
                self._insert_file_assets(conn, target_files, dirpath)

        # Compute scores for all folder nodes
        self._compute_all_scores(conn)

        # Bottom-up promotion: if all children of a folder are code projects,
        # promote the parent to code project too
        self._promote_code_parents(conn)

        # Save scan metadata
        conn.execute(
            "INSERT OR REPLACE INTO scan_meta (key, value) VALUES (?, ?)",
            ("last_scan_time", self.scan_time)
        )
        conn.execute(
            "INSERT OR REPLACE INTO scan_meta (key, value) VALUES (?, ?)",
            ("scan_roots", json.dumps(self.scan_roots, ensure_ascii=False))
        )
        conn.commit()
        conn.close()

        summary = {
            "scan_time": self.scan_time,
            "roots": self.scan_roots,
            "total_folders": total_folders,
            "total_files": total_files,
            "skipped_dirs": skipped_dirs,
            "db_path": self.db_path,
        }

        logger.info(
            f"✅ Scan complete: {total_folders} folders, "
            f"{total_files} files, {skipped_dirs} dirs skipped"
        )

        return summary

    def _collect_target_files(
        self, dirpath: str, filenames: List[str]
    ) -> List[Dict[str, Any]]:
        """Collect metadata for target files in a directory."""
        target_files = []

        for fname in filenames:
            # Skip Office temporary lock files (~$xxx.docx, ~$xxx.xlsx, etc.)
            if fname.startswith("~$"):
                continue

            # Handle iCloud stub files: .filename.icloud → filename
            is_cloud_only = False
            real_name = fname
            if fname.startswith(".") and fname.endswith(".icloud"):
                real_name = fname[1:-7]  # strip leading . and trailing .icloud
                is_cloud_only = True
                if not real_name:  # safety check
                    continue

            ext = Path(real_name).suffix.lstrip(".").lower()
            if ext not in TARGET_EXTENSIONS:
                continue

            fpath = os.path.join(dirpath, fname)
            try:
                stat = os.stat(fpath)
                if stat.st_size < MIN_FILE_SIZE:
                    continue

                file_size = stat.st_size
                # iCloud stubs are tiny; mark size as 0 to signal "unknown"
                if is_cloud_only:
                    file_size = 0

                target_files.append({
                    "path": fpath,
                    "name": real_name,
                    "ext": ext,
                    "type_group": TYPE_GROUPS.get(ext, "other"),
                    "size": file_size,
                    "mtime": datetime.fromtimestamp(
                        stat.st_mtime
                    ).isoformat(timespec="seconds"),
                    "is_cloud_only": is_cloud_only,
                    "content_hash": self._compute_file_hash(fpath)
                        if ext in ("jpg", "jpeg", "png")
                        and not is_cloud_only
                        and "CloudStorage" not in fpath
                        and "Mobile Documents" not in fpath
                        else None,
                })
            except (OSError, PermissionError):
                continue

        return target_files

    @staticmethod
    def _compute_file_hash(filepath: str, chunk_size: int = 8192) -> Optional[str]:
        """Compute SHA256 hash of the first chunk_size bytes of a file.
        Fast and sufficient for image dedup detection.
        """
        try:
            with open(filepath, "rb") as f:
                data = f.read(chunk_size)
            return hashlib.sha256(data).hexdigest()
        except (OSError, PermissionError):
            return None

    def _build_folder_node(
        self, dirpath: str, scan_root: str, files: List[Dict],
        is_code_project: bool = False
    ) -> Dict[str, Any]:
        """Build a folder node dict from collected file metadata."""
        # Calculate depth relative to scan root
        try:
            rel = os.path.relpath(dirpath, scan_root)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
        except ValueError:
            depth = 0

        parent = str(Path(dirpath).parent)

        type_counts = {"document": 0, "spreadsheet": 0, "image": 0,
                       "structured_data": 0, "presentation": 0, "other": 0}
        total_size = 0
        latest_mtime = ""

        for f in files:
            tg = f["type_group"]
            type_counts[tg] = type_counts.get(tg, 0) + 1
            total_size += f["size"]
            if f["mtime"] > latest_mtime:
                latest_mtime = f["mtime"]

        return {
            "path": dirpath,
            "parent": parent,
            "depth": depth,
            "file_count": len(files),
            "total_size": total_size,
            "doc_count": type_counts["document"],
            "sheet_count": type_counts["spreadsheet"],
            "image_count": type_counts["image"],
            "data_count": type_counts["structured_data"],
            "pres_count": type_counts["presentation"],
            "is_code_project": is_code_project,
            "latest_mtime": latest_mtime,
            "scan_time": self.scan_time,
        }

    def _insert_folder_node(self, conn: sqlite3.Connection, node: Dict):
        """Insert a folder node into the database."""
        conn.execute(
            """INSERT OR REPLACE INTO folder_nodes 
            (path, parent, depth, file_count, total_size, 
             doc_count, sheet_count, image_count, data_count, pres_count,
             is_code_project, latest_mtime, scan_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node["path"], node["parent"], node["depth"],
                node["file_count"], node["total_size"],
                node["doc_count"], node["sheet_count"],
                node["image_count"], node["data_count"], node["pres_count"],
                1 if node["is_code_project"] else 0,
                node["latest_mtime"], node["scan_time"],
            )
        )
        conn.commit()

    def _insert_file_assets(
        self, conn: sqlite3.Connection, files: List[Dict], folder: str
    ):
        """Insert file assets into the database."""
        conn.executemany(
            """INSERT OR REPLACE INTO file_assets 
            (path, folder, name, ext, type_group, size, mtime,
             content_hash, scan_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (f["path"], folder, f["name"], f["ext"],
                 f["type_group"], f["size"], f["mtime"],
                 f.get("content_hash"), self.scan_time)
                for f in files
            ]
        )
        conn.commit()

    # ==================== Scoring ====================

    def _compute_all_scores(self, conn: sqlite3.Connection):
        """Compute value scores for all folder nodes."""
        rows = conn.execute("SELECT * FROM folder_nodes").fetchall()

        if not rows:
            return

        # Find max total_size for normalization
        max_size = max(r["total_size"] for r in rows) or 1

        now = datetime.now()

        for row in rows:
            score = self._compute_score(row, max_size, now)
            conn.execute(
                "UPDATE folder_nodes SET score = ? WHERE path = ?",
                (round(score, 4), row["path"])
            )

        conn.commit()

    def _compute_score(
        self, row: sqlite3.Row, max_size: int, now: datetime
    ) -> float:
        """
        Compute value score for a folder node.

        score = 0.4 × knowledge_file_ratio
              + 0.3 × log_normalized_size
              + 0.3 × recency_score
        """
        total = row["file_count"] or 1

        # Factor 1: Knowledge file ratio (documents + spreadsheets + presentations)
        knowledge_count = (
            row["doc_count"] + row["sheet_count"] + row["pres_count"]
        )
        knowledge_ratio = knowledge_count / total

        # Factor 2: Log-normalized size (avoid huge folders dominating)
        if row["total_size"] > 0 and max_size > 0:
            log_size = math.log1p(row["total_size"]) / math.log1p(max_size)
        else:
            log_size = 0.0

        # Factor 3: Recency score
        recency = 0.1  # default for very old
        if row["latest_mtime"]:
            try:
                mtime = datetime.fromisoformat(row["latest_mtime"])
                days_ago = (now - mtime).days
                if days_ago <= 7:
                    recency = 1.0
                elif days_ago <= 30:
                    recency = 0.7
                elif days_ago <= 90:
                    recency = 0.5
                elif days_ago <= 365:
                    recency = 0.3
                else:
                    recency = 0.1
            except (ValueError, TypeError):
                pass

        return 0.4 * knowledge_ratio + 0.3 * log_size + 0.3 * recency

    # ==================== Query Methods ====================

    def get_high_value_nodes(
        self, min_score: float = 0.3, limit: int = 50
    ) -> List[Dict]:
        """Get folder nodes with score above threshold, ordered by score desc."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM folder_nodes 
            WHERE score >= ? ORDER BY score DESC LIMIT ?""",
            (min_score, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ==================== File-Level Scoring Constants ====================

    # Type priority tiers for file scoring
    # Tier 1 (1.0): Core knowledge documents — equal priority
    # Tier 2 (0.7): Lightweight text formats
    # Tier 3 (0.4): Structured data
    # Excluded: images (need OCR, V2)
    FILE_TYPE_PRIORITY: Dict[str, float] = {
        "pdf": 1.0, "docx": 1.0, "doc": 1.0,
        "xlsx": 1.0, "xls": 1.0,
        "pptx": 1.0, "ppt": 1.0,
        "md": 0.7, "txt": 0.7, "csv": 0.7,
        "json": 0.4,
    }

    # File scoring weights (5 factors)
    W_FOLDER = 0.20     # folder context
    W_TYPE = 0.15       # file type priority
    W_RECENCY = 0.30    # time freshness (most important)
    W_COPIES = 0.20     # duplication signal
    W_SUBSTANCE = 0.15  # file size / content richness

    # Extensions eligible for copy-count scoring
    # docs: use (size, ext) fingerprint; images: use content_hash
    COPY_DETECT_EXTS: Set[str] = {
        "pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt",
        "jpg", "jpeg", "png",
    }

    # Filenames to exclude from parse queue (code dependency files)
    EXCLUDE_FILENAMES: Set[str] = {
        "requirements.txt", "package.json", "package-lock.json",
        "yarn.lock", "poetry.lock", "pipfile.lock", "gemfile.lock",
        "tsconfig.json", ".eslintrc.json", ".prettierrc",
    }

    def build_parse_queue(
        self, limit: int = 100, export_path: str = None
    ) -> List[Dict]:
        """
        Build a ranked parse queue with file-level scoring.

        score = 0.25 × folder_score
              + 0.20 × type_priority
              + 0.30 × recency           # TODO V2: continuous decay function
              + 0.25 × copy_count_score   # TODO V2: content hash instead of size fingerprint

        Excludes: images (need OCR), iCloud-only files, 0-byte files.
        """
        conn = self._get_conn()

        # Step 1: Build copy count maps
        # Documents: use (size, ext) fingerprint (reliable for large files)
        doc_fingerprints = conn.execute("""
            SELECT size, ext, COUNT(*) as copies
            FROM file_assets
            WHERE size > 0
              AND ext IN ('pdf','docx','doc','xlsx','xls','pptx','ppt')
            GROUP BY size, ext
            HAVING copies > 1
        """).fetchall()
        doc_copy_map = {
            (r["size"], r["ext"]): r["copies"] for r in doc_fingerprints
        }

        # Images: use content_hash (accurate even for small files)
        img_fingerprints = conn.execute("""
            SELECT content_hash, COUNT(*) as copies
            FROM file_assets
            WHERE content_hash IS NOT NULL
              AND ext IN ('jpg','jpeg','png')
            GROUP BY content_hash
            HAVING copies > 1
        """).fetchall()
        img_hash_copies = {
            r["content_hash"]: r["copies"] for r in img_fingerprints
        }

        # Step 2: Get all scoreable files (exclude cloud-only, 0-byte)
        exclude_list = list(self.EXCLUDE_FILENAMES)
        placeholders = ",".join("?" for _ in exclude_list)
        query = f"""
            SELECT f.path, f.folder, f.name, f.ext, f.type_group,
                   f.size, f.mtime, f.content_hash,
                   n.score as folder_score
            FROM file_assets f
            JOIN folder_nodes n ON f.folder = n.path
            WHERE f.type_group != 'image'
              AND f.size > 0
              AND f.name NOT IN ({placeholders})
            ORDER BY f.path
        """
        rows = conn.execute(query, exclude_list).fetchall()

        # Find max file size for log normalization
        max_size_row = conn.execute(
            "SELECT MAX(size) FROM file_assets WHERE size > 0"
        ).fetchone()
        max_file_size = max_size_row[0] or 1

        now = datetime.now()
        scored_files = []

        for row in rows:
            row = dict(row)

            # Factor 1: Folder score (0-1)
            f_folder = row["folder_score"] or 0.0

            # Factor 2: Type priority
            f_type = self.FILE_TYPE_PRIORITY.get(row["ext"], 0.3)

            # Factor 3: Recency
            # TODO V2: Replace step function with continuous exponential decay
            f_recency = 0.1
            if row["mtime"]:
                try:
                    mtime = datetime.fromisoformat(row["mtime"])
                    days_ago = (now - mtime).days
                    if days_ago <= 7:
                        f_recency = 1.0
                    elif days_ago <= 30:
                        f_recency = 0.8
                    elif days_ago <= 90:
                        f_recency = 0.6
                    elif days_ago <= 365:
                        f_recency = 0.3
                    else:
                        f_recency = 0.1
                except (ValueError, TypeError):
                    pass

            # Factor 4: Copy count (only for whitelisted types)
            # docs → size fingerprint, images → content hash
            copies = 1
            if row["ext"] in self.COPY_DETECT_EXTS:
                if row["ext"] in ("jpg", "jpeg", "png"):
                    # Image: use content hash
                    if row.get("content_hash"):
                        copies = img_hash_copies.get(
                            row["content_hash"], 1
                        )
                else:
                    # Document: use size fingerprint
                    copies = doc_copy_map.get(
                        (row["size"], row["ext"]), 1
                    )

            if copies >= 4:
                f_copies = 1.0
            elif copies == 3:
                f_copies = 0.8
            elif copies == 2:
                f_copies = 0.6
            else:
                f_copies = 0.3

            # Factor 5: Substance — log-normalized file size
            # Larger files tend to contain more knowledge
            f_substance = (
                math.log1p(row["size"]) / math.log1p(max_file_size)
            )

            # Composite score
            file_score = (
                self.W_FOLDER * f_folder
                + self.W_TYPE * f_type
                + self.W_RECENCY * f_recency
                + self.W_COPIES * f_copies
                + self.W_SUBSTANCE * f_substance
            )

            row["file_score"] = round(file_score, 4)
            row["copies"] = copies
            row["scoring_detail"] = {
                "folder": round(self.W_FOLDER * f_folder, 4),
                "type": round(self.W_TYPE * f_type, 4),
                "recency": round(self.W_RECENCY * f_recency, 4),
                "copies": round(self.W_COPIES * f_copies, 4),
                "substance": round(self.W_SUBSTANCE * f_substance, 4),
            }
            # Remove content_hash from output
            row.pop("content_hash", None)
            scored_files.append(row)

        conn.close()

        # Deduplicate: for files with same (size, ext) fingerprint,
        # keep only the copy with the highest file_score
        seen_fingerprints = {}
        deduped = []
        for f in scored_files:
            fp = (f["size"], f["ext"])
            if fp in seen_fingerprints:
                # Already have a higher-scored copy, skip
                continue
            seen_fingerprints[fp] = True
            deduped.append(f)

        # Sort by file_score descending, take top N
        deduped.sort(key=lambda x: x["file_score"], reverse=True)
        queue = deduped[:limit]

        # Add rank
        for i, item in enumerate(queue, 1):
            item["rank"] = i

        # Export if requested
        if export_path:
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(queue, f, ensure_ascii=False, indent=2)
            logger.info(
                f"📋 Parse queue exported: {len(queue)} files → {export_path}"
            )

        return queue

    def build_user_profile(
        self, export_path: str = None
    ) -> Dict[str, Any]:
        """
        Build a user knowledge profile by aggregating top-level folder domains.

        TODO V2: Use LLM for domain classification and keyword extraction
        TODO V2: Add temporal activity tracking
        """
        conn = self._get_conn()

        # Get scan roots
        scan_roots_row = conn.execute(
            "SELECT value FROM scan_meta WHERE key = 'scan_roots'"
        ).fetchone()
        scan_roots = json.loads(scan_roots_row[0]) if scan_roots_row else []

        scan_time_row = conn.execute(
            "SELECT value FROM scan_meta WHERE key = 'last_scan_time'"
        ).fetchone()
        scan_time = scan_time_row[0] if scan_time_row else None

        domains = []

        for root in scan_roots:
            root = os.path.expanduser(root)
            if not os.path.isdir(root):
                continue

            # For CloudStorage, drill one level deeper to get actual
            # service dirs (OneDrive-个人/) then their children
            effective_roots = [root]
            if "CloudStorage" in root or "Mobile Documents" in root:
                try:
                    effective_roots = [
                        os.path.join(root, d)
                        for d in os.listdir(root)
                        if os.path.isdir(os.path.join(root, d))
                        and not d.startswith(".")
                    ]
                except (PermissionError, OSError):
                    pass

            for effective_root in effective_roots:
                # Get direct children that are in folder_nodes
                children = conn.execute("""
                    SELECT DISTINCT
                        CASE
                            WHEN INSTR(SUBSTR(path, LENGTH(?) + 2), '/') > 0
                            THEN SUBSTR(path, 1,
                                 LENGTH(?) + 1 +
                                 INSTR(SUBSTR(path, LENGTH(?) + 2), '/') - 1)
                            ELSE path
                        END as domain_path
                    FROM folder_nodes
                    WHERE path LIKE ? || '/%'
                """, (effective_root, effective_root, effective_root,
                      effective_root)).fetchall()

                # Deduplicate domain paths
                seen = set()
                for c in children:
                    dp = c["domain_path"]
                    if dp in seen:
                        continue
                    seen.add(dp)

                    domain_name = os.path.basename(dp)

                    # Aggregate all descendant stats
                    agg = conn.execute("""
                        SELECT
                            COUNT(*) as folder_count,
                            COALESCE(SUM(file_count), 0) as total_files,
                            COALESCE(SUM(total_size), 0) as total_size,
                            COALESCE(SUM(doc_count), 0) as documents,
                            COALESCE(SUM(sheet_count), 0) as spreadsheets,
                            COALESCE(SUM(image_count), 0) as images,
                            COALESCE(SUM(data_count), 0) as structured_data,
                            COALESCE(SUM(pres_count), 0) as presentations,
                            MAX(latest_mtime) as latest_activity
                        FROM folder_nodes
                        WHERE path = ? OR path LIKE ? || '/%'
                    """, (dp, dp)).fetchone()

                    if not agg or agg["total_files"] == 0:
                        continue

                    # Extract keywords from subfolder names
                    # TODO V2: Use LLM or NLP for smarter keyword extraction
                    subfolder_names = conn.execute("""
                        SELECT DISTINCT path FROM folder_nodes
                        WHERE (path = ? OR path LIKE ? || '/%')
                    """, (dp, dp)).fetchall()

                    keywords = set()
                    for sf in subfolder_names:
                        name = os.path.basename(sf["path"])
                        if len(name) >= 2 and not name.isdigit():
                            keywords.add(name)

                    keyword_list = sorted(keywords)[:20]

                    # Determine activity level
                    activity = "unknown"
                    if agg["latest_activity"]:
                        try:
                            latest = datetime.fromisoformat(
                                agg["latest_activity"]
                            )
                            days_ago = (datetime.now() - latest).days
                            if days_ago <= 30:
                                activity = "high"
                            elif days_ago <= 180:
                                activity = "medium"
                            else:
                                activity = "low"
                        except (ValueError, TypeError):
                            pass

                    type_dist = {}
                    if agg["documents"]:
                        type_dist["documents"] = agg["documents"]
                    if agg["spreadsheets"]:
                        type_dist["spreadsheets"] = agg["spreadsheets"]
                    if agg["images"]:
                        type_dist["images"] = agg["images"]
                    if agg["structured_data"]:
                        type_dist["structured_data"] = agg["structured_data"]
                    if agg["presentations"]:
                        type_dist["presentations"] = agg["presentations"]

                    domains.append({
                        "name": domain_name,
                        "root_path": dp,
                        "total_folders": agg["folder_count"],
                        "total_files": agg["total_files"],
                        "total_size_mb": round(
                            agg["total_size"] / (1024*1024), 2
                        ),
                        "type_distribution": type_dist,
                        "activity": activity,
                        "keywords": keyword_list,
                    })

        conn.close()

        # Sort domains by total_files descending
        domains.sort(key=lambda d: d["total_files"], reverse=True)

        profile = {
            "scan_time": scan_time,
            "total_domains": len(domains),
            "domains": domains,
            # TODO V2: Add LLM-generated summary
        }

        if export_path:
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(profile, f, ensure_ascii=False, indent=2)
            logger.info(
                f"👤 User profile exported: {len(domains)} domains → {export_path}"
            )

        return profile

    # Keep old method for backward compat
    def get_parse_queue(
        self, min_score: float = 0.3, limit: int = 200
    ) -> List[Dict]:
        """Legacy parse queue (folder-score only). Use build_parse_queue() instead."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT f.path, f.folder, f.name, f.ext, f.type_group,
                      f.size, f.mtime, n.score as folder_score
            FROM file_assets f
            JOIN folder_nodes n ON f.folder = n.path
            WHERE n.score >= ?
            ORDER BY n.score DESC, f.size DESC
            LIMIT ?""",
            (min_score, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_stats(self) -> Dict[str, Any]:
        """Get summary statistics of the current ontology."""
        conn = self._get_conn()

        folder_count = conn.execute(
            "SELECT COUNT(*) FROM folder_nodes"
        ).fetchone()[0]
        file_count = conn.execute(
            "SELECT COUNT(*) FROM file_assets"
        ).fetchone()[0]
        total_size = conn.execute(
            "SELECT COALESCE(SUM(total_size), 0) FROM folder_nodes"
        ).fetchone()[0]

        # Type distribution
        type_dist = {}
        for row in conn.execute(
            "SELECT type_group, COUNT(*) as cnt FROM file_assets GROUP BY type_group"
        ):
            type_dist[row["type_group"]] = row["cnt"]

        # Extension distribution
        ext_dist = {}
        for row in conn.execute(
            "SELECT ext, COUNT(*) as cnt FROM file_assets GROUP BY ext ORDER BY cnt DESC"
        ):
            ext_dist[row["ext"]] = row["cnt"]

        # Score distribution
        score_dist = {}
        for row in conn.execute(
            """SELECT 
                SUM(CASE WHEN score >= 0.7 THEN 1 ELSE 0 END) as high,
                SUM(CASE WHEN score >= 0.4 AND score < 0.7 THEN 1 ELSE 0 END) as medium,
                SUM(CASE WHEN score >= 0.1 AND score < 0.4 THEN 1 ELSE 0 END) as low,
                SUM(CASE WHEN score < 0.1 THEN 1 ELSE 0 END) as minimal
            FROM folder_nodes"""
        ):
            score_dist = {
                "high (≥0.7)": row["high"] or 0,
                "medium (0.4-0.7)": row["medium"] or 0,
                "low (0.1-0.4)": row["low"] or 0,
                "minimal (<0.1)": row["minimal"] or 0,
            }

        last_scan = conn.execute(
            "SELECT value FROM scan_meta WHERE key = 'last_scan_time'"
        ).fetchone()

        conn.close()

        return {
            "last_scan_time": last_scan[0] if last_scan else None,
            "total_folders": folder_count,
            "total_files": file_count,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "type_distribution": type_dist,
            "extension_distribution": ext_dist,
            "score_distribution": score_dist,
        }

    # ==================== Export ====================

    def export_json(self, output_path: str = None) -> str:
        """
        Export the ontology to a nested JSON file.
        Each folder node embeds its file list directly.

        Returns:
            Path to the exported JSON file.
        """
        if output_path is None:
            output_path = self.db_path.replace(".db", ".json")

        conn = self._get_conn()

        # Load all folders
        folders = [
            dict(r) for r in
            conn.execute(
                "SELECT * FROM folder_nodes ORDER BY path ASC"
            ).fetchall()
        ]

        # Load all files grouped by folder
        all_files = conn.execute(
            "SELECT * FROM file_assets ORDER BY folder, name"
        ).fetchall()

        # Group files by folder path
        files_by_folder: Dict[str, List[Dict]] = {}
        for f in all_files:
            fd = dict(f)
            folder_path = fd.pop("folder")
            fd.pop("scan_time", None)  # remove redundant scan_time
            fd.pop("path", None)       # remove redundant full path (name is sufficient)
            files_by_folder.setdefault(folder_path, []).append(fd)

        # Nest files into each folder node
        for node in folders:
            node["is_code_project"] = bool(node.get("is_code_project", 0))
            node["files"] = files_by_folder.get(node["path"], [])

        last_scan = conn.execute(
            "SELECT value FROM scan_meta WHERE key = 'last_scan_time'"
        ).fetchone()
        scan_roots = conn.execute(
            "SELECT value FROM scan_meta WHERE key = 'scan_roots'"
        ).fetchone()

        conn.close()

        data = {
            "scan_time": last_scan[0] if last_scan else None,
            "scan_roots": json.loads(scan_roots[0]) if scan_roots else [],
            "summary": self.get_stats(),
            "nodes": folders,
        }

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"📄 Exported ontology to {output_path}")
        return output_path

    def export_tree_json(self, output_path: str) -> str:
        """
        Export the ontology as a hierarchical tree JSON rooted at scan roots.

        Synthesizes intermediate parent nodes (directories that contain no
        target files themselves) to produce a proper, fully-connected tree.

        Each recorded folder node carries file-type counts:
        doc, sheet, pres, image, data.

        Returns:
            Path to the exported tree JSON file.
        """
        conn = self._get_conn()

        rows = conn.execute(
            "SELECT * FROM folder_nodes ORDER BY path ASC"
        ).fetchall()

        scan_roots_row = conn.execute(
            "SELECT value FROM scan_meta WHERE key = 'scan_roots'"
        ).fetchone()
        scan_roots = (
            json.loads(scan_roots_row[0]) if scan_roots_row else []
        )
        scan_roots = [os.path.expanduser(r) for r in scan_roots]

        conn.close()

        # ---- Helper: ensure a node exists for `path`, creating
        #      virtual parents up to the nearest scan_root as needed ----
        node_map: Dict[str, Dict[str, Any]] = {}

        def _find_scan_root(p: str) -> Optional[str]:
            """Return the scan root that contains path `p`, or None."""
            for sr in scan_roots:
                if p == sr or p.startswith(sr + os.sep):
                    return sr
            return None

        def _ensure_node(path: str) -> Dict[str, Any]:
            """Get or create a (possibly virtual) tree node for `path`."""
            if path in node_map:
                return node_map[path]

            node: Dict[str, Any] = {
                "name": os.path.basename(path) or path,
                "path": path,
                "children": [],
            }
            node_map[path] = node

            # Walk up to parent unless we're already at a scan root
            if path not in scan_roots:
                parent_path = str(Path(path).parent)
                sr = _find_scan_root(path)
                if sr and (parent_path == sr
                           or parent_path.startswith(sr + os.sep)):
                    parent_node = _ensure_node(parent_path)
                    parent_node["children"].append(node)

            return node

        # ---- Populate nodes from DB rows ----
        for r in rows:
            r = dict(r)
            path = r["path"]
            node = _ensure_node(path)

            # Attach type counts & score
            has_files = (r["file_count"] or 0) > 0
            if has_files:
                counts: Dict[str, int] = {}
                if r["doc_count"]:
                    counts["doc"] = r["doc_count"]
                if r["sheet_count"]:
                    counts["sheet"] = r["sheet_count"]
                if r["pres_count"]:
                    counts["pres"] = r["pres_count"]
                if r["image_count"]:
                    counts["image"] = r["image_count"]
                if r["data_count"]:
                    counts["data"] = r["data_count"]
                if counts:
                    node["file_types"] = counts
                node["file_count"] = r["file_count"]
                node["total_size"] = r["total_size"]
                node["score"] = r["score"]

            if r["is_code_project"]:
                node["is_code_project"] = True

        # ---- Collect roots (scan root nodes or orphan nodes) ----
        root_nodes: List[Dict[str, Any]] = []
        for sr in scan_roots:
            if sr in node_map:
                root_nodes.append(node_map[sr])

        # ---- Recursive cleanup: sort children, remove empty lists ----
        def _clean(n: Dict) -> Dict:
            children = n.get("children", [])
            if children:
                children.sort(key=lambda c: c["name"])
                n["children"] = [_clean(c) for c in children]
            else:
                n.pop("children", None)
            return n

        root_nodes = [_clean(r) for r in root_nodes]

        tree = {
            "scan_roots": scan_roots,
            "total_nodes": len(node_map),
            "tree": root_nodes,
        }

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)

        logger.info(
            f"🌳 Tree exported: {len(node_map)} nodes → {output_path}"
        )
        return output_path


# Default output directory (relative to knowhereapi-main/apps/worker/)
_DEFAULT_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "tmp_res", "ontology"
)


def quick_scan(
    roots: List[str] = None,
    db_path: str = None,
    output_dir: str = None,
    min_score: float = 0.3,
    export: bool = True,
    build_queue: bool = True,
    build_profile: bool = True,
    build_tree: bool = True,
) -> Dict[str, Any]:
    """
    One-line convenience function to scan, score, and export all outputs.

    Usage:
        from apps.worker.app.services.ontology_scanner import quick_scan
        result = quick_scan()

    Args:
        roots: Scan root directories (default: ~/Documents, ~/Desktop, etc.)
        db_path: SQLite output path
        output_dir: Directory for all outputs (default: tmp_res/ontology/)
        min_score: Minimum score for high-value nodes
        export: Whether to export ontology JSON
        build_queue: Whether to build parse queue
        build_profile: Whether to build user profile

    Returns:
        Dict with scan summary, stats, top nodes, parse queue, profile.
    """
    _output_dir = output_dir or _DEFAULT_OUTPUT_DIR
    os.makedirs(_output_dir, exist_ok=True)

    _db_path = db_path or os.path.join(_output_dir, "ontology.db")
    _roots = roots or DEFAULT_SCAN_ROOTS

    scanner = FileSystemScanner(scan_roots=_roots, db_path=_db_path)
    scan_summary = scanner.scan()
    stats = scanner.get_stats()
    top_nodes = scanner.get_high_value_nodes(min_score=min_score, limit=10)

    json_path = None
    if export:
        json_path = scanner.export_json(
            os.path.join(_output_dir, "ontology.json")
        )

    parse_queue = None
    if build_queue:
        parse_queue = scanner.build_parse_queue(
            limit=100,
            export_path=os.path.join(_output_dir, "parse_queue.json")
        )

    tree_path = None
    if build_tree:
        tree_path = scanner.export_tree_json(
            os.path.join(_output_dir, "tree.json")
        )

    profile = None
    if build_profile:
        profile = scanner.build_user_profile(
            export_path=os.path.join(_output_dir, "user_profile.json")
        )

    # Print summary to console
    print("\n" + "=" * 60)
    print(f"🔍 Scan Results — {scan_summary['scan_time']}")
    print("=" * 60)
    print(f"📂 Folders with target files: {stats['total_folders']}")
    print(f"📄 Total target files: {stats['total_files']}")
    print(f"💾 Total size: {stats['total_size_mb']} MB")
    print(f"\n📊 Type distribution: {stats['type_distribution']}")
    print(f"📊 Score distribution: {stats['score_distribution']}")

    if top_nodes:
        print(f"\n🏆 Top {len(top_nodes)} high-value folders:")
        for i, node in enumerate(top_nodes[:10], 1):
            size_mb = round(node["total_size"] / (1024 * 1024), 2)
            print(
                f"  {i}. [{node['score']:.2f}] {node['path']} "
                f"({node['file_count']} files, {size_mb} MB)"
            )

    print(f"\n📦 Output directory: {_output_dir}")
    print(f"🗄️  SQLite DB: {_db_path}")
    if tree_path:
        print(f"🌳 Tree JSON: {tree_path}")
    if json_path:
        print(f"📄 Ontology JSON: {json_path}")
    if parse_queue:
        print(f"📋 Parse queue: {len(parse_queue)} files")
    if profile:
        print(f"👤 User profile: {profile['total_domains']} domains")
    print("=" * 60 + "\n")

    return {
        "scan_summary": scan_summary,
        "stats": stats,
        "top_nodes": top_nodes,
        "parse_queue": parse_queue,
        "user_profile": profile,
        "output_dir": _output_dir,
        "json_path": json_path,
        "tree_path": tree_path,
    }
