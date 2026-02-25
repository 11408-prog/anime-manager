import sqlite3
from contextlib import contextmanager
from typing import List, Tuple, Optional, Dict

class ImageDatabaseError(Exception):
    pass

class DuplicateImageError(ImageDatabaseError):
    pass

class ImageDatabase:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self):
        """初始化表结构，包含标签多对多关系，并添加 is_private 字段"""
        with self.get_connection() as conn:
            # 清理可能遗留的旧表
            conn.execute("DROP TABLE IF EXISTS images_old")

            # 图片主表
            conn.execute('''CREATE TABLE IF NOT EXISTS images
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE,
                display_name TEXT,
                category TEXT DEFAULT '',
                phash TEXT,
                favorite INTEGER DEFAULT 0)''')

            # 标签表
            conn.execute('''CREATE TABLE IF NOT EXISTS tags
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE)''')

            # 图片-标签关联表
            conn.execute('''CREATE TABLE IF NOT EXISTS image_tags
                (image_id INTEGER,
                tag_id INTEGER,
                FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE,
                FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY(image_id, tag_id))''')

            # 检查并添加 is_private 字段
            cursor = conn.execute("PRAGMA table_info(images)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'is_private' not in columns:
                conn.execute("ALTER TABLE images ADD COLUMN is_private INTEGER DEFAULT 0")

            # 索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_images_favorite ON images(favorite)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_images_is_private ON images(is_private)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_images_category ON images(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_image_tags_tag_id ON image_tags(tag_id)")

            # 可选：从旧表迁移数据（如果存在旧表且有 tags 列）
            self._migrate_from_old_schema(conn)

    def _migrate_from_old_schema(self, conn):
        """检查旧表结构，将数据迁移到新结构（仅执行一次）"""
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='images_old'")
        if cursor.fetchone():
            return  # 已迁移过，跳过
        # 检查当前 images 表是否有 tags 列
        cursor = conn.execute("PRAGMA table_info(images)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'tags' in columns:
            # 将旧表重命名，创建新表，并复制数据（忽略 tags 列）
            conn.execute("ALTER TABLE images RENAME TO images_old")
            # 重新创建新表（上面已经创建，但可能已存在？这里确保重新创建）
            conn.execute('''CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE,
                display_name TEXT,
                category TEXT DEFAULT '',
                phash TEXT,
                favorite INTEGER DEFAULT 0,
                is_private INTEGER DEFAULT 0)''')
            # 复制数据（忽略 tags 列）
            conn.execute('''INSERT INTO images (filename, display_name, category, phash, favorite)
                SELECT filename, display_name, category, phash, favorite FROM images_old''')
            # 迁移标签：从 images_old.tags 解析并插入到 tags 和 image_tags
            rows = conn.execute("SELECT id, tags FROM images_old WHERE tags IS NOT NULL AND tags != ''").fetchall()
            for img_id, tags_str in rows:
                tags = self._split_tags(tags_str)
                for tag in tags:
                    # 获取或创建标签 ID
                    tag_id = self._get_or_create_tag(conn, tag)
                    # 插入关联
                    conn.execute("INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)", (img_id, tag_id))
            # 删除旧表
            conn.execute("DROP TABLE images_old")

    @staticmethod
    def _split_tags(tags_str: str) -> List[str]:
        if not tags_str:
            return []
        return [tag.strip() for tag in tags_str.split(',') if tag.strip()]

    def _get_or_create_tag(self, conn, tag_name: str) -> int:
        """获取标签 ID，不存在则创建"""
        cur = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
        return cur.lastrowid

    # ---------- 核心操作 ----------
    def add_image(self, filename: str, display_name: str, category: str, tags_str: str,
                  phash: Optional[str] = None, is_private: bool = False) -> None:
        """
        添加图片，默认 is_private=False
        """
        try:
            with self.get_connection() as conn:
                cur = conn.execute(
                    "INSERT INTO images (filename, display_name, category, phash, is_private) VALUES (?, ?, ?, ?, ?)",
                    (filename, display_name, category, phash, 1 if is_private else 0)
                )
                image_id = cur.lastrowid
                tags = self._split_tags(tags_str)
                for tag in tags:
                    tag_id = self._get_or_create_tag(conn, tag)
                    conn.execute("INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))
        except sqlite3.IntegrityError as e:
            raise DuplicateImageError(f"图片 '{filename}' 已存在") from e
        except sqlite3.Error as e:
            raise ImageDatabaseError(f"数据库错误: {e}") from e

    def delete_image(self, filename: str) -> bool:
        try:
            with self.get_connection() as conn:
                cur = conn.execute("DELETE FROM images WHERE filename=?", (filename,))
                return cur.rowcount > 0
        except sqlite3.Error as e:
            raise ImageDatabaseError(f"删除失败: {e}") from e

    def update_image(self, filename: str, category: str, tags_str: str) -> bool:
        try:
            with self.get_connection() as conn:
                # 获取图片 ID
                cur = conn.execute("SELECT id FROM images WHERE filename=?", (filename,))
                row = cur.fetchone()
                if not row:
                    return False
                image_id = row[0]
                # 更新分类
                conn.execute("UPDATE images SET category=? WHERE id=?", (category, image_id))
                # 删除旧标签关联
                conn.execute("DELETE FROM image_tags WHERE image_id=?", (image_id,))
                # 插入新标签
                tags = self._split_tags(tags_str)
                for tag in tags:
                    tag_id = self._get_or_create_tag(conn, tag)
                    conn.execute("INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))
                return True
        except sqlite3.Error as e:
            raise ImageDatabaseError(f"更新失败: {e}") from e

    def search_images(self, search_term: str = "", category: Optional[str] = None,
                      favorite: Optional[bool] = None, private: Optional[bool] = None,
                      limit: int = 100, offset: int = 0) -> Tuple[List[Tuple], int]:
        """
        返回 (图片信息列表, 总记录数)
        每个图片信息为 (filename, display_name, category, tags_str, favorite, is_private)
        favorite: 普通收藏标记
        private: 私密标记
        """
        with self.get_connection() as conn:
            # 构建基础查询
            base_query = "FROM images WHERE 1=1"
            params = []
            if search_term:
                base_query += " AND id IN (SELECT image_id FROM image_tags WHERE tag_id IN (SELECT id FROM tags WHERE name LIKE ?))"
                params.append(f'%{search_term}%')
            if category:
                base_query += " AND category = ?"
                params.append(category)
            if favorite is not None:
                base_query += " AND favorite = ?"
                params.append(1 if favorite else 0)
            if private is not None:
                base_query += " AND is_private = ?"
                params.append(1 if private else 0)

            # 查询总数
            count_sql = f"SELECT COUNT(*) {base_query}"
            total = conn.execute(count_sql, params).fetchone()[0]

            # 查询数据，并拼接标签字符串
            data_sql = f"""
                SELECT images.id, images.filename, images.display_name, images.category,
                       images.favorite, images.is_private,
                       GROUP_CONCAT(tags.name, ', ') AS tags
                FROM images
                LEFT JOIN image_tags ON images.id = image_tags.image_id
                LEFT JOIN tags ON image_tags.tag_id = tags.id
                WHERE 1=1
            """
            # 复制条件
            if search_term:
                data_sql += " AND images.id IN (SELECT image_id FROM image_tags WHERE tag_id IN (SELECT id FROM tags WHERE name LIKE ?))"
            if category:
                data_sql += " AND images.category = ?"
            if favorite is not None:
                data_sql += " AND images.favorite = ?"
            if private is not None:
                data_sql += " AND images.is_private = ?"
            data_sql += " GROUP BY images.id ORDER BY images.id LIMIT ? OFFSET ?"
            data_params = params.copy()
            data_params.extend([limit, offset])

            rows = conn.execute(data_sql, data_params).fetchall()
            # 转换为 (filename, display_name, category, tags_str, favorite, is_private)
            result = [(row[1], row[2], row[3], row[6] or '', bool(row[4]), bool(row[5])) for row in rows]
            return result, total

    def get_all_tags(self) -> List[str]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
            return [row[0] for row in rows]

    def get_all_categories(self) -> List[str]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT DISTINCT category FROM images WHERE category != '' ORDER BY category").fetchall()
            return [row[0] for row in rows]

    def get_tag_frequencies(self) -> Dict[str, int]:
        with self.get_connection() as conn:
            rows = conn.execute('''
                SELECT tags.name, COUNT(image_tags.image_id) as cnt
                FROM tags
                LEFT JOIN image_tags ON tags.id = image_tags.tag_id
                GROUP BY tags.id
                ORDER BY cnt DESC
            ''').fetchall()
            return {row[0]: row[1] for row in rows if row[1] > 0}

    def get_hot_tags(self, limit: int = 10) -> List[str]:
        freq = self.get_tag_frequencies()
        return list(freq.keys())[:limit]

    # ---------- 普通收藏操作 ----------
    def set_favorite(self, filename: str, is_favorite: bool) -> None:
        """设置图片的普通收藏状态"""
        with self.get_connection() as conn:
            conn.execute("UPDATE images SET favorite=? WHERE filename=?", (1 if is_favorite else 0, filename))

    def get_favorites(self) -> List[str]:
        """获取所有普通收藏图片的文件名"""
        with self.get_connection() as conn:
            rows = conn.execute("SELECT filename FROM images WHERE favorite=1").fetchall()
            return [row[0] for row in rows]

    # ---------- 私密空间操作 ----------
    def set_private(self, filename: str, is_private: bool) -> None:
        """设置图片的私密状态"""
        with self.get_connection() as conn:
            conn.execute("UPDATE images SET is_private=? WHERE filename=?", (1 if is_private else 0, filename))

    def get_private_images(self) -> List[str]:
        """获取所有私密图片的文件名"""
        with self.get_connection() as conn:
            rows = conn.execute("SELECT filename FROM images WHERE is_private=1").fetchall()
            return [row[0] for row in rows]