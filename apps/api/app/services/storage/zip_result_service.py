"""
ZIP 结果包生成服务
根据 Knowhere-API-ZIP-Spec.md 规范生成 ZIP 包
"""
import hashlib
import json
import os
import tempfile
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from PIL import Image


class ZipResultService:
    """ZIP 结果包生成服务"""

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
    ) -> Tuple[str, Dict[str, str], Dict[str, Any], int]:
        """
        生成 ZIP 结果包

        Args:
            job_id: 任务ID
            chunks: chunks 数据列表
            add_dir: 解析目录路径（包含 images/ 和 tables/ 目录）
            source_file_name: 源文件名
            data_id: 用户自定义ID
            job_metadata: 任务元数据

        Returns:
            Tuple[zip_file_path, checksum, statistics, zip_size]:
            - zip_file_path: ZIP 文件路径
            - checksum: {"algorithm": "sha256", "value": "..."}
            - statistics: {"total_chunks": int, "text_chunks": int, "image_chunks": int, "table_chunks": int, "total_pages": Optional[int]}
            - zip_size: ZIP 文件大小（字节）
        """
        try:
            # 创建临时 ZIP 文件
            temp_dir = tempfile.gettempdir()
            zip_file_path = os.path.join(temp_dir, f"result_{job_id}.zip")

            # 统计 chunks 信息
            statistics = self._calculate_statistics(chunks)

            # 收集图片和表格文件信息（需要在格式化 chunks 之前，因为需要文件信息）
            images_dir = os.path.join(add_dir, "images")
            tables_dir = os.path.join(add_dir, "tables")
            image_files_info = self._collect_image_files(chunks, images_dir)
            table_files_info = self._collect_table_files(chunks, tables_dir)
            
            # 创建图片和表格文件的映射（chunk_id -> file_info）
            image_files_map = {img["id"]: img for img in image_files_info}
            table_files_map = {tb["id"]: tb for tb in table_files_info}
            
            # 转换 chunks 数据格式（使用文件信息）
            formatted_chunks = self._format_chunks(chunks, image_files_map, table_files_map)

            # 创建 ZIP 包
            with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                # 1. 生成 chunks.json
                chunks_json = json.dumps({"chunks": formatted_chunks}, ensure_ascii=False, indent=2)
                zip_file.writestr("chunks.json", chunks_json.encode("utf-8"))

                # 2. 尝试添加 full.md（如果存在）
                markdown_path = None
                full_md_path = os.path.join(add_dir, "full.md")
                if os.path.exists(full_md_path):
                    markdown_path = full_md_path
                    zip_file.write(full_md_path, "full.md")

                # 3. 添加图片文件
                for img_info in image_files_info:
                    source_path = img_info["source_path"]
                    if os.path.exists(source_path):
                        zip_file.write(
                            source_path,
                            img_info["zip_path"],
                        )
                    else:
                        logger.warning(f"图片文件不存在: {source_path}")

                # 4. 添加表格文件
                for table_info in table_files_info:
                    source_path = table_info["source_path"]
                    if os.path.exists(source_path):
                        zip_file.write(
                            source_path,
                            table_info["zip_path"],
                        )
                    else:
                        logger.warning(f"表格文件不存在: {source_path}")

                # 5. 生成 manifest.json（不包含 checksum，checksum 存储在数据库中）
                manifest = self._generate_manifest(
                    job_id=job_id,
                    data_id=data_id,
                    source_file_name=source_file_name,
                    statistics=statistics,
                    image_files_info=image_files_info,
                    table_files_info=table_files_info,
                    has_markdown=markdown_path is not None,
                )
                manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)
                zip_file.writestr("manifest.json", manifest_json.encode("utf-8"))

            # 计算 ZIP 包的 SHA-256
            checksum_value = self._calculate_zip_checksum(zip_file_path)
            checksum = {"algorithm": "sha256", "value": checksum_value}

            # 获取 ZIP 文件大小
            zip_size = os.path.getsize(zip_file_path)

            logger.info(
                f"ZIP 包生成成功: job_id={job_id}, size={zip_size}, checksum={checksum_value[:16]}..."
            )

            return zip_file_path, checksum, statistics, zip_size

        except Exception as e:
            logger.error(f"生成 ZIP 包失败: {e}")
            raise

    def _calculate_statistics(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算统计信息"""
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
            "total_pages": None,  # 暂时无法确定页数
        }

    def _format_chunks(
        self, 
        chunks: List[Dict[str, Any]], 
        image_files_map: Dict[str, Dict[str, Any]],
        table_files_map: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """将 chunks 数据转换为 ZIP 规范格式"""
        formatted = []
        for chunk in chunks:
            chunk_id = str(chunk.get("chunk_id") or chunk.get("know_id"))
            chunk_type_str = chunk.get("type", "")
            
            # 确定 chunk type
            if "IMAGE" in chunk_type_str:
                chunk_type = "image"
            elif "TABLE" in chunk_type_str:
                chunk_type = "table"
            else:
                chunk_type = "text"

            # 获取 content
            content = chunk.get("text") or chunk.get("content", "")

            # 清理 path（移除文件系统路径，只保留逻辑路径）
            path = self._clean_path(chunk.get("path", ""))

            # 构建 metadata
            metadata = {
                "length": len(content),
                "summary": chunk.get("summary"),
            }

            # 根据类型添加特定字段
            if chunk_type == "text":
                metadata["tokens"] = chunk.get("tokens")
                metadata["keywords"] = chunk.get("keywords", [])
                # relationships 需要从其他 chunks 中提取，暂时为空
                metadata["relationships"] = None
            elif chunk_type == "image":
                # 从 image_files_map 获取图片信息
                img_info = image_files_map.get(chunk_id)
                if img_info:
                    metadata["file_path"] = img_info["file_path"]
                    metadata["original_name"] = img_info["original_name"]
                else:
                    # 如果没有找到，使用默认值
                    metadata["file_path"] = f"images/{chunk_id}.jpg"
                    metadata["original_name"] = f"image_{chunk_id}.jpg"
                metadata["alt_text"] = chunk.get("summary")
            elif chunk_type == "table":
                # 从 table_files_map 获取表格信息
                tb_info = table_files_map.get(chunk_id)
                if tb_info:
                    metadata["file_path"] = tb_info["file_path"]
                    metadata["original_name"] = tb_info["original_name"]
                else:
                    # 如果没有找到，使用默认值
                    metadata["file_path"] = f"tables/{chunk_id}.html"
                    metadata["original_name"] = f"table_{chunk_id}.html"
                metadata["table_type"] = None

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
        """清理 path，只保留逻辑路径"""
        if not path:
            return "/"
        
        # 移除文件系统路径前缀
        # 例如：.-->users-->KB_DATA_xxx-->目录-->文件.pdf-->章节-->小节
        # 应该提取：章节-->小节
        
        # 查找最后一个 .pdf、.docx 等文件扩展名
        import re

        # 匹配文件名模式（包含扩展名）
        file_pattern = r'[^/]+\.(pdf|docx|doc|txt|md|xlsx|xls|pptx|ppt)'
        match = re.search(file_pattern, path, re.IGNORECASE)
        
        if match:
            # 提取文件名后的部分
            path_after_file = path[match.end():]
            # 清理路径分隔符
            path_after_file = path_after_file.replace("-->", "/").strip("/")
            if path_after_file:
                return path_after_file
        
        # 如果找不到文件模式，尝试清理常见前缀
        path = path.replace("-->", "/")
        # 移除开头的路径分隔符和空段
        path = "/".join([p for p in path.split("/") if p and p not in ["", ".", "users"]])
        return path if path else "/"

    def _collect_image_files(
        self, chunks: List[Dict[str, Any]], images_dir: str
    ) -> List[Dict[str, Any]]:
        """收集图片文件信息"""
        image_files = []
        
        if not os.path.exists(images_dir):
            return image_files

        # 获取所有图片文件
        image_files_map = {}
        for filename in os.listdir(images_dir):
            file_path = os.path.join(images_dir, filename)
            if os.path.isfile(file_path):
                image_files_map[filename] = file_path

        # 从 chunks 中匹配图片
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id") or chunk.get("know_id")
            chunk_type = chunk.get("type", "")
            
            if "IMAGE" not in chunk_type:
                continue

            # 尝试从 chunk 的 path 字段获取原始文件名
            original_path = chunk.get("path", "")
            if original_path:
                # 统一处理路径分隔符：将 --> 替换为 /，然后提取文件名
                normalized_path = original_path.replace("-->", "/")
                original_name = os.path.basename(normalized_path)
            else:
                original_name = None
            
            # 如果找不到原始文件名，尝试从 images_dir 中查找
            if not original_name:
                # 尝试匹配 chunk_id 相关的文件
                for filename in image_files_map.keys():
                    if str(chunk_id) in filename or filename.startswith("图"):
                        original_name = filename
                        break

            # 获取文件扩展名
            if original_name:
                _, ext = os.path.splitext(original_name)
                ext = ext.lstrip(".") or "jpg"
            else:
                ext = "jpg"

            source_path = None
            if original_name and original_name in image_files_map:
                source_path = image_files_map[original_name]
            else:
                # 如果找不到，使用第一个未使用的图片文件
                for filename, file_path in image_files_map.items():
                    if filename not in [img["original_name"] for img in image_files]:
                        source_path = file_path
                        original_name = filename
                        _, ext = os.path.splitext(filename)
                        ext = ext.lstrip(".") or "jpg"
                        break

            if not source_path:
                logger.warning(f"无法找到图片文件: chunk_id={chunk_id}, original_name={original_name}")
                continue

            # 获取图片尺寸
            width = None
            height = None
            try:
                with Image.open(source_path) as img:
                    width, height = img.size
            except Exception:
                pass

            file_size = os.path.getsize(source_path)
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
        """收集表格文件信息"""
        table_files = []
        
        if not os.path.exists(tables_dir):
            return table_files

        # 获取所有表格文件
        table_files_map = {}
        for filename in os.listdir(tables_dir):
            file_path = os.path.join(tables_dir, filename)
            if os.path.isfile(file_path) and filename.endswith(".html"):
                table_files_map[filename] = file_path

        # 从 chunks 中匹配表格
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id") or chunk.get("know_id")
            chunk_type = chunk.get("type", "")
            
            if "TABLE" not in chunk_type:
                continue

            # 尝试从 chunk 的 path 字段获取原始文件名
            original_path = chunk.get("path", "")
            if original_path:
                # 统一处理路径分隔符：将 --> 替换为 /，然后提取文件名
                normalized_path = original_path.replace("-->", "/")
                original_name = os.path.basename(normalized_path)
            else:
                original_name = None
            
            # 如果找不到原始文件名，尝试从 tables_dir 中查找
            if not original_name:
                # 尝试匹配 chunk_id 相关的文件
                for filename in table_files_map.keys():
                    if str(chunk_id) in filename or filename.startswith("表"):
                        original_name = filename
                        break

            source_path = None
            if original_name and original_name in table_files_map:
                source_path = table_files_map[original_name]
            else:
                # 如果找不到，使用第一个未使用的表格文件
                for filename, file_path in table_files_map.items():
                    if filename not in [tb["original_name"] for tb in table_files]:
                        source_path = file_path
                        original_name = filename
                        break

            if not source_path:
                logger.warning(f"无法找到表格文件: chunk_id={chunk_id}, original_name={original_name}")
                continue

            file_size = os.path.getsize(source_path)
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
    ) -> Dict[str, Any]:
        """生成 manifest.json"""
        # 准备 images 数组（移除内部字段）
        images = []
        for img_info in image_files_info:
            images.append({
                "id": img_info["id"],
                "file_path": img_info["file_path"],
                "original_name": img_info["original_name"],
                "size_bytes": img_info["size_bytes"],
                "format": img_info["format"],
                "width": img_info.get("width"),
                "height": img_info.get("height"),
            })

        # 准备 tables 数组（移除内部字段）
        tables = []
        for table_info in table_files_info:
            tables.append({
                "id": table_info["id"],
                "file_path": table_info["file_path"],
                "original_name": table_info["original_name"],
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
                "images": images,
                "tables": tables,
            },
        }

        return manifest

    def _calculate_zip_checksum(self, zip_file_path: str) -> str:
        """计算 ZIP 文件的 SHA-256 校验和"""
        sha256_hash = hashlib.sha256()
        with open(zip_file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest().lower()

