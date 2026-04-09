"""
ZIP Result Package Generation Service
Generates ZIP packages according to Knowhere-API-ZIP-Spec.md specification
"""
import hashlib
import io
import json
import os
import tempfile
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from loguru import logger
from PIL import Image

if TYPE_CHECKING:
    import pandas as pd

from shared.core.exceptions.domain_exceptions import StorageServiceException, KnowhereException


class ZipResultService:
    """ZIP Result Package Generation Service"""

    def __init__(self):
        pass

    def generate_zip_package(
        self,
        job_id: str,
        chunks: List[Dict[str, Any]],
        add_dir: str,
        source_file_name: str,
        data_id: Optional[str],
        job_metadata: Dict[str, Any],
        parsed_df: Optional["pd.DataFrame"] = None,
        temp_dir: Optional[str] = None,
    ) -> Tuple[str, Dict[str, str], Dict[str, Any], int]:
        """
        Generate ZIP result package

        Args:
            job_id: Job ID
            chunks: List of chunks data
            add_dir: Parsed directory path (contains images/ and tables/ directories)
            source_file_name: Source file name
            data_id: User-defined ID
            job_metadata: Job metadata
            parsed_df: Optional, parsed DataFrame for generating kb.csv and hierarchy.json
            temp_dir: Optional directory for the generated ZIP file

        Returns:
            Tuple[zip_file_path, checksum, statistics, zip_size]:
            - zip_file_path: ZIP file path
            - checksum: {"algorithm": "sha256", "value": "..."}
            - statistics: {"total_chunks": int, "text_chunks": int, "image_chunks": int, "table_chunks": int, "total_pages": Optional[int]}
            - zip_size: ZIP file size in bytes
        """
        try:
            # Create temporary ZIP file
            effective_temp_dir = temp_dir or tempfile.gettempdir()
            os.makedirs(effective_temp_dir, exist_ok=True)
            zip_file_path = os.path.join(effective_temp_dir, f"result_{job_id}.zip")

            # Calculate chunks statistics
            statistics = self._calculate_statistics(chunks)

            # Collect image and table file info (must be done before formatting chunks as file info is needed)
            images_dir = os.path.join(add_dir, "images")
            tables_dir = os.path.join(add_dir, "tables")
            image_files_info = self._collect_image_files(chunks, images_dir)
            table_files_info = self._collect_table_files(chunks, tables_dir)
            
            # Create image and table file mappings (chunk_id -> file_info)
            image_files_map = {img["id"]: img for img in image_files_info}
            table_files_map = {tb["id"]: tb for tb in table_files_info}
            
            # Convert chunks data format (using file info)
            formatted_chunks = self._format_chunks(chunks, image_files_map, table_files_map)

            # Create ZIP package
            with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                # 1. Generate chunks.json (full version)
                chunks_json = json.dumps({"chunks": formatted_chunks}, ensure_ascii=False, indent=2)
                zip_file.writestr("chunks.json", chunks_json.encode("utf-8"))

                # 1b. Generate chunks_slim.json for retrieval-time chunk routing.
                slim_chunks = []
                for fc in formatted_chunks:
                    summary = " ".join(str((fc.get("metadata") or {}).get("summary", "") or "").split())
                    content = " ".join(str(fc.get("content", "") or "").split())
                    slim = {
                        "type": fc.get("type", "text"),
                        "path": fc.get("path", ""),
                        "content": summary or content[:300],
                    }
                    slim_chunks.append(slim)
                slim_json = json.dumps({"chunks": slim_chunks}, ensure_ascii=False, indent=2)
                zip_file.writestr("chunks_slim.json", slim_json.encode("utf-8"))

                # 2. Try to add full.md (if exists)
                markdown_path = None
                full_md_path = os.path.join(add_dir, "full.md")
                if os.path.exists(full_md_path):
                    markdown_path = full_md_path
                    zip_file.write(full_md_path, "full.md")

                # 2b. Try to add toc_hierarchies.json (if exists)
                has_toc = False
                toc_path = os.path.join(add_dir, "toc_hierarchies.json")
                if os.path.exists(toc_path):
                    zip_file.write(toc_path, "toc_hierarchies.json")
                    has_toc = True
                    logger.info("Added toc_hierarchies.json to ZIP")

                # 3. Add image files
                for img_info in image_files_info:
                    source_path = img_info["source_path"]
                    if os.path.exists(source_path):
                        zip_file.write(
                            source_path,
                            img_info["zip_path"],
                        )
                    else:
                        logger.warning(f"Image file not found: {source_path}")

                # 4. Add table files
                for table_info in table_files_info:
                    source_path = table_info["source_path"]
                    if os.path.exists(source_path):
                        zip_file.write(
                            source_path,
                            table_info["zip_path"],
                        )
                    else:
                        logger.warning(f"Table file not found: {source_path}")

                # 5. Generate kb.csv and hierarchy.json (if parsed_df is provided)
                has_kb_csv = False
                has_hierarchy = False
                if parsed_df is not None and len(parsed_df) > 0:
                    # 5a. Generate kb.csv (using UTF-8 with BOM encoding for Excel compatibility)
                    csv_buffer = io.StringIO()
                    parsed_df.to_csv(csv_buffer, index=False, encoding='utf-8')
                    # Add BOM header (\ufeff) to ensure Excel recognizes UTF-8
                    csv_content = '\ufeff' + csv_buffer.getvalue()
                    zip_file.writestr("kb.csv", csv_content.encode("utf-8"))
                    has_kb_csv = True
                    logger.info(f"Added kb.csv with {len(parsed_df)} rows")
                    
                    # 5b. Generate hierarchy.json from parsed_df path column
                    if 'path' in parsed_df.columns:
                        path_list = parsed_df['path'].dropna().tolist()
                        hierarchy_dict = self._restore_graph_by_paths(path_list)
                        hierarchy_json = json.dumps(hierarchy_dict, ensure_ascii=False, indent=4)
                        zip_file.writestr("hierarchy.json", hierarchy_json.encode("utf-8"))
                        has_hierarchy = True
                        logger.info(f"Added hierarchy.json")
                        
                        # 5c. 生成 hierarchy_view.html
                        try:
                            from shared.services.storage.hierarchy_html_generator import generate_hierarchy_html
                            chunks_dict = {"chunks": formatted_chunks}
                            html_content = generate_hierarchy_html(hierarchy_dict, chunks_dict)
                            zip_file.writestr("hierarchy_view.html", html_content.encode("utf-8"))
                        except Exception as e:
                            logger.warning(f"genearte hierarchy_view.html fail {e}")

                # 6. Generate manifest.json (checksum not included, stored in database)
                manifest = self._generate_manifest(
                    job_id=job_id,
                    data_id=data_id,
                    source_file_name=source_file_name,
                    statistics=statistics,
                    image_files_info=image_files_info,
                    table_files_info=table_files_info,
                    has_markdown=markdown_path is not None,
                    has_kb_csv=has_kb_csv,
                    has_hierarchy=has_hierarchy,
                    has_toc=has_toc,
                )
                manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)
                zip_file.writestr("manifest.json", manifest_json.encode("utf-8"))

            # Calculate ZIP package SHA-256
            checksum_value = self._calculate_zip_checksum(zip_file_path)
            checksum = {"algorithm": "sha256", "value": checksum_value}

            # Get ZIP file size
            zip_size = os.path.getsize(zip_file_path)

            logger.info(
                f"ZIP package generated successfully: job_id={job_id}, size={zip_size}, checksum={checksum_value[:16]}..."
            )

            return zip_file_path, checksum, statistics, zip_size

        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Failed to generate ZIP package: {e}")
            raise StorageServiceException(
                internal_message=f"Failed to generate ZIP package: {str(e)}",
                operation="generate_zip_package",
                original_exception=e
            )

    def _calculate_statistics(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate statistics"""
        total_chunks = len(chunks)
        text_chunks = 0
        image_chunks = 0
        table_chunks = 0

        for chunk in chunks:
            chunk_type = chunk.get("type", "")
            if "IMAGE" in chunk_type or chunk_type == "image":
                image_chunks += 1
            elif "TABLE" in chunk_type or chunk_type == "table":
                table_chunks += 1
            else:
                text_chunks += 1

        return {
            "total_chunks": total_chunks,
            "text_chunks": text_chunks,
            "image_chunks": image_chunks,
            "table_chunks": table_chunks,
            "total_pages": None,  # Cannot determine page count at this point
        }

    def _format_chunks(
        self, 
        chunks: List[Dict[str, Any]], 
        image_files_map: Dict[str, Dict[str, Any]],
        table_files_map: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert chunks data to ZIP specification format"""
        
        def safe_parse_rels(type_val, connects):
            """Safely parse relationship fields"""
            rels = []
            # Extract relationships from type field (multi-line format)
            if type_val and isinstance(type_val, str):
                if "\n" in type_val:
                    rels.extend([line.strip() for line in type_val.split("\n")[1:-1] if line.strip()])
            # Extract relationships from connectto field
            if connects:
                if isinstance(connects, list):
                    rels.extend([str(c).strip() for c in connects if c])
                elif isinstance(connects, str):
                    if "\n" in connects:
                        rels.extend([line.strip() for line in connects.split("\n") if line.strip()])
                    else:
                        rels.append(connects.strip())
            return rels if rels else []
        
        formatted = []
        for chunk in chunks:
            chunk_id = str(chunk.get("chunk_id") or chunk.get("know_id"))
            chunk_type_str = chunk.get("type", "")
            
            # Determine chunk type
            if "IMAGE" in chunk_type_str.upper() or chunk_type_str == "image":
                chunk_type = "image"
            elif "TABLE" in chunk_type_str.upper() or chunk_type_str == "table":
                chunk_type = "table"
            else:
                chunk_type = "text"

            # Get content
            content = chunk.get("text") or chunk.get("content", "")

            # Use original path directly to match kb.csv
            path = chunk.get("path", "")

            # Get or build base metadata
            existing_metadata = chunk.get("metadata", {})
            metadata = {
                "length": existing_metadata.get("length") or len(content),
                "summary": existing_metadata.get("summary") or chunk.get("summary", ""),
                "page_nums": existing_metadata.get("page_nums", []),
            }

            # Add type-specific fields
            if chunk_type == "text":
                metadata["tokens"] = existing_metadata.get("tokens") or chunk.get("tokens", 0)
                metadata["keywords"] = existing_metadata.get("keywords") or chunk.get("keywords", [])
                
                # Try to extract relationships from metadata or original fields
                relationships = existing_metadata.get("relationships")
                if not relationships:
                    # Try to parse from type and connectto fields
                    type_val = chunk.get("type_raw") or chunk_type_str
                    connects = chunk.get("connectto")
                    relationships = safe_parse_rels(type_val, connects)
                
                metadata["relationships"] = relationships if relationships else []
                
            elif chunk_type == "image":
                # Get image info from existing_metadata or image_files_map
                file_path = existing_metadata.get("file_path")
                
                if not file_path:
                    # Get image info from image_files_map
                    img_info = image_files_map.get(chunk_id)
                    if img_info:
                        file_path = img_info["file_path"]
                    else:
                        # Extract from path or use default
                        img_name = path.split("/")[-1] if "/" in path else f"image_{chunk_id}.jpg"
                        file_path = f"images/{img_name}"
                
                metadata["file_path"] = file_path
                # Unified schema: include keywords and tokens for all chunk types
                metadata["keywords"] = existing_metadata.get("keywords") or chunk.get("keywords", [])
                metadata["tokens"] = []
                
            elif chunk_type == "table":
                # Get table info from existing_metadata or table_files_map
                file_path = existing_metadata.get("file_path")
                
                if not file_path:
                    # Get table info from table_files_map
                    tb_info = table_files_map.get(chunk_id)
                    if tb_info:
                        file_path = tb_info["file_path"]
                    else:
                        # Extract from path or use default
                        tbl_name = path.split("/")[-1] if "/" in path else f"table_{chunk_id}.html"
                        file_path = f"tables/{tbl_name}"
                
                metadata["file_path"] = file_path
                # Unified schema: include keywords and tokens for all chunk types
                metadata["keywords"] = existing_metadata.get("keywords") or chunk.get("keywords", [])
                metadata["tokens"] = []

            formatted_chunk = {
                "chunk_id": chunk_id,
                "type": chunk_type,
                "content": content,
                "path": path,
                "metadata": metadata,
            }
            formatted.append(formatted_chunk)

        return formatted

    def _clean_path(self, path: str) -> str:
        """Clean path, keep only logical path"""
        if not path:
            return "/"
        
        # Remove filesystem path prefix
        # Example: .-->users-->KB_DATA_xxx-->dir-->file.pdf-->chapter-->section
        # Should extract: chapter-->section
        
        # Find the last .pdf, .docx, etc. file extension
        import re

        # Match filename pattern (with extension)
        file_pattern = r'[^/]+\.(pdf|docx|doc|txt|md|xlsx|xls|pptx|ppt)'
        match = re.search(file_pattern, path, re.IGNORECASE)
        
        if match:
            # Extract the part after filename
            path_after_file = path[match.end():]
            # Clean path separators
            path_after_file = path_after_file.replace("-->", "/").strip("/")
            if path_after_file:
                return path_after_file
        
        # If no file pattern found, try to clean common prefixes
        path = path.replace("-->", "/")
        # Remove leading path separators and empty segments
        path = "/".join([p for p in path.split("/") if p and p not in ["", ".", "users"]])
        return path if path else "/"

    def _collect_image_files(
        self, chunks: List[Dict[str, Any]], images_dir: str
    ) -> List[Dict[str, Any]]:
        """Collect image file information"""
        image_files = []
        if not os.path.exists(images_dir):
            return image_files

        # Get all image files
        image_files_map = {}
        for filename in os.listdir(images_dir):
            file_path = os.path.join(images_dir, filename)
            if os.path.isfile(file_path):
                image_files_map[filename] = file_path
        # Match images from chunks
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id") or chunk.get("know_id")
            chunk_type = chunk.get("type", "")
            
            # Support standardized type: "image" or legacy format "IMAGE_xxx"
            if chunk_type != "image" and "IMAGE" not in chunk_type:
                continue

            # Try to get original filename from chunk's path field
            original_path = chunk.get("path", "")
            if original_path:
                # Normalize path separators: replace --> with /, then extract filename
                normalized_path = original_path.replace("-->", "/")
                original_name = os.path.basename(normalized_path)
            else:
                original_name = None
            
            # If original filename not found, try to find from images_dir
            if not original_name:
                # Try to match files related to chunk_id
                for filename in image_files_map.keys():
                    if str(chunk_id) in filename or filename.startswith("图"):
                        original_name = filename
                        break

            # Get file extension
            if original_name:
                _, ext = os.path.splitext(original_name)
                ext = ext.lstrip(".") or "jpg"
            else:
                ext = "jpg"

            source_path = None
            if original_name and original_name in image_files_map:
                source_path = image_files_map[original_name]
            else:
                # If not found, use the first unused image file
                for filename, file_path in image_files_map.items():
                    if filename not in [img["original_name"] for img in image_files]:
                        source_path = file_path
                        original_name = filename
                        _, ext = os.path.splitext(filename)
                        ext = ext.lstrip(".") or "jpg"
                        break

            if not source_path:
                logger.warning(
                    f"Cannot find image file: chunk_id={chunk_id}, original_name={original_name}"
                )
                continue

            # Get image dimensions
            width = None
            height = None
            try:
                with Image.open(source_path) as img:
                    width, height = img.size
            except Exception:
                pass

            file_size = os.path.getsize(source_path)
            
            # Priority: use file_path from metadata, then original_name, finally chunk_id
            metadata = chunk.get("metadata", {})
            if metadata and isinstance(metadata, dict):
                # metadata.file_path format: "images/xxx.jpg"
                zip_file_path = metadata.get("file_path")
                if zip_file_path and zip_file_path.startswith("images/"):
                    # Use complete path from metadata
                    zip_path = zip_file_path
                    # Extract filename as original_name
                    if not original_name:
                        original_name = metadata.get("original_name") or os.path.basename(zip_file_path)
                else:
                    # If metadata has no file_path, use original_name or chunk_id
                    if original_name:
                        zip_path = f"images/{original_name}"
                    else:
                        zip_path = f"images/{chunk_id}.{ext}"
            else:
                # If no metadata, use original_name or chunk_id
                if original_name:
                    zip_path = f"images/{original_name}"
                else:
                    zip_path = f"images/{chunk_id}.{ext}"

            image_files.append({
                "id": str(chunk_id),
                "file_path": zip_path,
                "original_name": original_name or f"image_{chunk_id}.{ext}",
                "size_bytes": file_size,
                "format": ext.lower(),
                "width": width,
                "height": height,
                "source_path": source_path,
                "zip_path": zip_path,
            })

        return image_files

    def _collect_table_files(
        self, chunks: List[Dict[str, Any]], tables_dir: str
    ) -> List[Dict[str, Any]]:
        """Collect table file information"""
        table_files = []
        if not os.path.exists(tables_dir):
            return table_files

        # Get all table files
        table_files_map = {}
        for filename in os.listdir(tables_dir):
            file_path = os.path.join(tables_dir, filename)
            if os.path.isfile(file_path) and filename.endswith(".html"):
                table_files_map[filename] = file_path
        # Match tables from chunks
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id") or chunk.get("know_id")
            chunk_type = chunk.get("type", "")
            
            # Support standardized type: "table" or legacy format "TABLE_xxx"
            if chunk_type != "table" and "TABLE" not in chunk_type:
                continue

            # Try to get original filename from chunk's path field
            original_path = chunk.get("path", "")
            if original_path:
                # Normalize path separators: replace --> with /, then extract filename
                normalized_path = original_path.replace("-->", "/")
                original_name = os.path.basename(normalized_path)
            else:
                original_name = None
            
            # If original filename not found, try to find from tables_dir
            if not original_name:
                # Try to match files related to chunk_id
                for filename in table_files_map.keys():
                    if str(chunk_id) in filename or filename.startswith("表"):
                        original_name = filename
                        break

            source_path = None
            if original_name and original_name in table_files_map:
                source_path = table_files_map[original_name]
            else:
                # If not found, use the first unused table file
                for filename, file_path in table_files_map.items():
                    if filename not in [tb["original_name"] for tb in table_files]:
                        source_path = file_path
                        original_name = filename
                        break

            if not source_path:
                logger.warning(
                    f"Cannot find table file: chunk_id={chunk_id}, original_name={original_name}"
                )
                continue

            file_size = os.path.getsize(source_path)
            
            # Priority: use file_path from metadata, then original_name, finally chunk_id
            metadata = chunk.get("metadata", {})
            if metadata and isinstance(metadata, dict):
                # metadata.file_path format: "tables/xxx.html"
                zip_file_path = metadata.get("file_path")
                if zip_file_path and zip_file_path.startswith("tables/"):
                    # Use complete path from metadata
                    zip_path = zip_file_path
                    # Extract filename as original_name
                    if not original_name:
                        original_name = metadata.get("original_name") or os.path.basename(zip_file_path)
                else:
                    # If metadata has no file_path, use original_name or chunk_id
                    if original_name:
                        zip_path = f"tables/{original_name}"
                    else:
                        zip_path = f"tables/{chunk_id}.html"
            else:
                # If no metadata, use original_name or chunk_id
                if original_name:
                    zip_path = f"tables/{original_name}"
                else:
                    zip_path = f"tables/{chunk_id}.html"

            table_files.append({
                "id": str(chunk_id),
                "file_path": zip_path,
                "original_name": original_name or f"table_{chunk_id}.html",
                "size_bytes": file_size,
                "format": "html",
                "source_path": source_path,
                "zip_path": zip_path,
            })

        return table_files

    def _generate_manifest(
        self,
        job_id: str,
        data_id: Optional[str],
        source_file_name: str,
        statistics: Dict[str, Any],
        image_files_info: List[Dict[str, Any]],
        table_files_info: List[Dict[str, Any]],
        has_markdown: bool = False,
        has_kb_csv: bool = False,
        has_hierarchy: bool = False,
        has_toc: bool = False,
    ) -> Dict[str, Any]:
        """Generate manifest.json"""
        # Prepare images array (keep only necessary fields: id, file_path, size_bytes, format, width, height)
        images = []
        for img_info in image_files_info:
            images.append({
                "id": img_info["id"],
                "file_path": img_info["file_path"],
                "size_bytes": img_info["size_bytes"],
                "format": img_info["format"],
                "width": img_info.get("width"),
                "height": img_info.get("height"),
            })

        # Prepare tables array (keep only necessary fields: id, file_path, size_bytes, format)
        tables = []
        for table_info in table_files_info:
            tables.append({
                "id": table_info["id"],
                "file_path": table_info["file_path"],
                "size_bytes": table_info["size_bytes"],
                "format": table_info["format"],
            })

        manifest = {
            "version": "1.0",
            "job_id": job_id,
            "data_id": data_id,
            "source_file_name": source_file_name,
            "processing_date": datetime.utcnow().isoformat() + "Z",
            "statistics": statistics,
            "files": {
                "chunks": "chunks.json",
                "markdown": "full.md" if has_markdown else None,
                "kb_csv": "kb.csv" if has_kb_csv else None,
                "hierarchy": "hierarchy.json" if has_hierarchy else None,
                "toc_hierarchies": "toc_hierarchies.json" if has_toc else None,
                "images": images,
                "tables": tables,
            },
        }

        return manifest

    def _calculate_zip_checksum(self, zip_file_path: str) -> str:
        """Calculate SHA-256 checksum of ZIP file"""
        sha256_hash = hashlib.sha256()
        with open(zip_file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest().lower()

    def _restore_graph_by_paths(self, paths: List[str]) -> Dict[str, Any]:
        """
        Rebuild hierarchical structure from path list
        
        Args:
            paths: Path list, e.g. ["dir/file.pdf/chapter1/section1", "dir/file.pdf/chapter2"]
        
        Returns:
            Nested dict structure, e.g. {"dir": {"file.pdf": {"chapter1": {"section1": {}}, "chapter2": {}}}}
        """
        root_dict: Dict[str, Any] = {}
        
        # Support multiple separators
        for path in paths:
            if not path:
                continue
            
            # Only normalize '-->' legacy separator; do NOT replace '\' since
            # heading text may contain LaTeX backslashes (e.g. \mathrm, \mathbf)
            normalized_path = path.replace("-->", "/")
            nodes = [n.strip() for n in normalized_path.split("/") if n.strip()]
            
            current_dict = root_dict
            for node in nodes:
                if node not in current_dict:
                    current_dict[node] = {}
                current_dict = current_dict[node]
        
        return root_dict
