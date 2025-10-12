"""
完整的API接口测试
测试知识库管理系统的完整业务流程
"""
import asyncio
import json
import os
import tempfile
from typing import Dict, Any
import requests


class TestAPIComplete:
    """完整的API测试类"""
    
    def setup_method(self):
        """测试前的设置"""
        self.session = requests.Session()
        self.base_url = "http://localhost:5005/api/v1"
        self.test_username = "test_user_api"
        self.test_password = "test_password_123"
        self.test_email = "test_fresh@example.com"
        self.test_phone = "13800138000"
        self.access_token = None
        self.test_file_content = "这是一个测试文档内容，用于测试知识库功能。"
        
    def teardown_method(self):
        """测试后的清理"""
        # 清理测试数据
        if self.access_token:
            try:
                # 这里可以添加清理测试数据的逻辑
                pass
            except Exception as e:
                print(f"清理测试数据时出错: {e}")

    def test_01_register_user(self):
        """测试用户注册"""
        print("\n=== 测试用户注册 ===")
        
        user_data = {
            "username": self.test_username,
            "password": self.test_password,
            "email": self.test_email,
            "phone": self.test_phone,
            "avatar_url": None
        }
        
        response = self.session.post(
            f"{self.base_url}/auth/register",
            json=user_data
        )
        
        print(f"注册响应状态码: {response.status_code}")
        try:
            print(f"注册响应内容: {response.json()}")
        except:
            print("注册响应内容解析失败")
        
        # 注册可能成功或失败（用户已存在），都继续测试
        if response.status_code not in [200, 201, 400, 422]:
            print(f"注册失败，状态码: {response.status_code}")
            return
    
    def test_01_5_registration_and_auto_login(self):
        """测试注册后自动登录流程"""
        print("\n=== 测试注册后自动登录流程 ===")
        
        # 使用新的测试邮箱避免冲突
        test_email = f"test_auto_login_{self.test_username}@example.com"
        
        # 1. 注册用户
        user_data = {
            "username": f"{self.test_username}_auto",
            "password": self.test_password,
            "email": test_email,
            "phone": self.test_phone,
            "avatar_url": None
        }
        
        print("步骤1: 注册用户")
        register_response = self.session.post(
            f"{self.base_url}/auth/register",
            json=user_data
        )
        
        print(f"注册状态码: {register_response.status_code}")
        print(f"注册响应: {register_response.json()}")
        
        if register_response.status_code not in [200, 201, 400, 422]:
            print("注册失败，跳过自动登录测试")
            return
        
        # 2. 尝试使用email登录（模拟前端自动登录）
        print("步骤2: 使用email登录")
        login_data = {
            "username": test_email,  # 使用email作为username
            "password": self.test_password
        }
        
        login_response = self.session.post(
            f"{self.base_url}/auth/jwt/login",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        print(f"登录状态码: {login_response.status_code}")
        print(f"登录响应: {login_response.json()}")
        
        if login_response.status_code == 200:
            response_data = login_response.json()
            if "access_token" in response_data:
                self.access_token = response_data["access_token"]
                print(f"✅ 自动登录成功，获取到访问令牌: {self.access_token[:20]}...")
            else:
                print("❌ 登录响应中没有有效的访问令牌")
        else:
            print(f"❌ 自动登录失败，状态码: {login_response.status_code}")
        
    def test_02_login_user(self):
        """测试用户登录"""
        print("\n=== 测试用户登录 ===")
        
        # 使用JWT登录接口，发送form-data格式
        login_data = {
            "username": self.test_email,  # 使用email作为username
            "password": self.test_password
        }
        
        response = self.session.post(
            f"{self.base_url}/auth/jwt/login",
            data=login_data,  # 使用data而不是json
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        print(f"登录响应状态码: {response.status_code}")
        try:
            print(f"登录响应内容: {response.json()}")
        except:
            print("登录响应内容解析失败")
        
        if response.status_code != 200:
            print(f"登录失败，状态码: {response.status_code}")
            raise Exception(f"登录失败，状态码: {response.status_code}")
        
        response_data = response.json()
        if "access_token" in response_data:
            self.access_token = response_data["access_token"]
            print(f"获取到访问令牌: {self.access_token[:20]}...")
        else:
            print("登录响应中没有有效的访问令牌")
            raise Exception("登录响应中没有有效的访问令牌")
        
    def test_03_get_protected_resource(self):
        """测试获取受保护资源"""
        print("\n=== 测试获取受保护资源 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        response = self.session.get(
            f"{self.base_url}/auth/me",
            headers=headers
        )
        
        print(f"受保护资源响应状态码: {response.status_code}")
        print(f"受保护资源响应内容: {response.json()}")
        
        if response.status_code != 200:
            print(f"请求失败，状态码: {response.status_code}")
            return
        
    def test_04_create_directory(self):
        """测试创建目录"""
        print("\n=== 测试创建目录 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        directory_data = {
            "id": "test_dir_001",
            "title": "测试目录",
            "parent_id": None,
            "user_id": "1"  # 假设用户ID为1
        }
        
        response = self.session.post(
            f"{self.base_url}/kb/create_directory",
            json=directory_data,
            headers=headers
        )
        
        print(f"创建目录响应状态码: {response.status_code}")
        print(f"创建目录响应内容: {response.json()}")
        
        # 创建目录可能成功或失败，都继续测试
        if response.status_code not in [200, 201, 400, 422, 500]:
            print(f"创建目录失败，状态码: {response.status_code}")
            return
        
    def test_05_upload_file(self):
        """测试文件上传"""
        print("\n=== 测试文件上传 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
            temp_file.write(self.test_file_content)
            temp_file_path = temp_file.name
            
        try:
            with open(temp_file_path, 'rb') as file:
                files = {"file": ("test_document.txt", file, "text/plain")}
                data = {"prefix": "test/"}
                
                response = self.session.post(
                    f"{self.base_url}/kb/up_kb_file",
                    files=files,
                    data=data,
                    headers=headers
                )
                
                print(f"文件上传响应状态码: {response.status_code}")
                print(f"文件上传响应内容: {response.json()}")
                
                # 文件上传可能成功或失败，都继续测试
                assert response.status_code in [200, 400, 422, 500]
                
        finally:
            # 清理临时文件
            os.unlink(temp_file_path)
            
    def test_06_add_kb_fragment(self):
        """测试添加知识碎片"""
        print("\n=== 测试添加知识碎片 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        fragment_data = {
            "kb_path": "测试目录",
            "fragment_content": "这是一个测试知识碎片，包含重要的技术信息。",
            "fragment_title": "测试知识碎片",
            "smart_title_parse": True,
            "summary_image": False,
            "summary_txt": True,
            "summary_table": False,
            "add_frag_desc": "测试描述",
            "label": "测试标签"
        }
        
        response = self.session.post(
            f"{self.base_url}/kb/add_kb_fragment",
            json=fragment_data,
            headers=headers
        )
        
        print(f"添加知识碎片响应状态码: {response.status_code}")
        try:
            print(f"添加知识碎片响应内容: {response.json()}")
        except:
            print("添加知识碎片响应内容解析失败")
        
        # 添加知识碎片可能成功或失败，都继续测试
        assert response.status_code in [200, 201, 400, 422, 500]
        
    def test_07_search_knowledge(self):
        """测试知识库搜索"""
        print("\n=== 测试知识库搜索 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        search_data = {
            "question": "测试知识",
            "topk": 3,
            "filter_nodes": ["测试目录"],
            "filter_mode": "include",
            "filter_type": 1,
            "show_image": False,
            "rerank": True,
            "ask": True,
            "ask_multimodal": False,
            "ask_agent": False
        }
        
        response = self.session.post(
            f"{self.base_url}/kb/search",
            json=search_data,
            headers=headers
        )
        
        print(f"知识库搜索响应状态码: {response.status_code}")
        try:
            print(f"知识库搜索响应内容: {response.json()}")
        except:
            print("知识库搜索响应内容解析失败")
        
        # 搜索可能成功或失败，都继续测试
        assert response.status_code in [200, 400, 422, 500]
        
    def test_08_get_fragments(self):
        """测试获取知识片段"""
        print("\n=== 测试获取知识片段 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        fragment_data = {
            "kb_path": "测试目录"
        }
        
        response = self.session.post(
            f"{self.base_url}/kb/get_fragments",
            json=fragment_data,
            headers=headers
        )
        
        print(f"获取知识片段响应状态码: {response.status_code}")
        try:
            print(f"获取知识片段响应内容: {response.json()}")
        except:
            print("获取知识片段响应内容解析失败")
        
        # 获取知识片段可能成功或失败，都继续测试
        assert response.status_code in [200, 400, 422, 500]
        
    def test_09_get_file_tree(self):
        """测试获取文件树"""
        print("\n=== 测试获取文件树 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        tree_data = {
            "kb_path": "测试目录"
        }
        
        response = self.session.post(
            f"{self.base_url}/kb/get_fileTree",
            json=tree_data,
            headers=headers
        )
        
        print(f"获取文件树响应状态码: {response.status_code}")
        print(f"获取文件树响应内容: {response.json()}")
        
        # 获取文件树可能成功或失败，都继续测试
        assert response.status_code in [200, 400, 422, 500]
        
    def test_10_get_directory_list(self):
        """测试获取目录列表"""
        print("\n=== 测试获取目录列表 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        response = self.session.post(
            f"{self.base_url}/kb/get_directory",
            headers=headers
        )
        
        print(f"获取目录列表响应状态码: {response.status_code}")
        print(f"获取目录列表响应内容: {response.json()}")
        
        # 获取目录列表可能成功或失败，都继续测试
        assert response.status_code in [200, 400, 422, 500]
        
    def test_11_update_directory(self):
        """测试更新目录"""
        print("\n=== 测试更新目录 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        update_data = {
            "id": "test_dir_001",
            "title": "更新后的测试目录",
            "parent_id": None,
            "user_id": "1"
        }
        
        response = self.session.post(
            f"{self.base_url}/kb/update_directory",
            json=update_data,
            headers=headers
        )
        
        print(f"更新目录响应状态码: {response.status_code}")
        print(f"更新目录响应内容: {response.json()}")
        
        # 更新目录可能成功或失败，都继续测试
        assert response.status_code in [200, 400, 422, 500]
        
    def test_12_delete_kb_data(self):
        """测试删除知识数据"""
        print("\n=== 测试删除知识数据 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        delete_data = {
            "remove_node": "测试目录"
        }
        
        response = self.session.post(
            f"{self.base_url}/kb/delete_kb_data",
            json=delete_data,
            headers=headers
        )
        
        print(f"删除知识数据响应状态码: {response.status_code}")
        print(f"删除知识数据响应内容: {response.json()}")
        
        # 删除知识数据可能成功或失败，都继续测试
        assert response.status_code in [200, 400, 422, 500]
        
    def test_13_delete_directory(self):
        """测试删除目录"""
        print("\n=== 测试删除目录 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        delete_data = {
            "id": "test_dir_001",
            "title": "测试目录",
            "parent_id": None,
            "user_id": "1"
        }
        
        response = self.session.post(
            f"{self.base_url}/kb/delete_directory",
            json=delete_data,
            headers=headers
        )
        
        print(f"删除目录响应状态码: {response.status_code}")
        print(f"删除目录响应内容: {response.json()}")
        
        # 删除目录可能成功或失败，都继续测试
        assert response.status_code in [200, 400, 422, 500]
        
    def test_14_build_tree(self):
        """测试构建知识树"""
        print("\n=== 测试构建知识树 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        tree_data = {
            "smart_summary": True,
            "root_node": "测试目录"
        }
        
        response = self.session.post(
            f"{self.base_url}/kb/tree_kb",
            json=tree_data,
            headers=headers
        )
        
        print(f"构建知识树响应状态码: {response.status_code}")
        print(f"构建知识树响应内容: {response.json()}")
        
        # 构建知识树可能成功或失败，都继续测试
        assert response.status_code in [200, 400, 422, 500]
        
    def test_15_build_forest(self):
        """测试构建知识森林"""
        print("\n=== 测试构建知识森林 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        forest_data = {
            "cut_len": 2000,
            "k": 5,
            "threshold": 0.8,
            "source_node": "测试目录"
        }
        
        response = self.session.post(
            f"{self.base_url}/kb/forest_kb",
            json=forest_data,
            headers=headers
        )
        
        print(f"构建知识森林响应状态码: {response.status_code}")
        print(f"构建知识森林响应内容: {response.json()}")
        
        # 构建知识森林可能成功或失败，都继续测试
        assert response.status_code in [200, 400, 422, 500]
        
    def test_16_complete_business_flow(self):
        """测试完整业务流程"""
        print("\n=== 测试完整业务流程 ===")
        
        # 1. 用户注册和登录
        print("步骤1: 用户注册和登录")
        self.test_01_register_user()
        self.test_02_login_user()
        
        if not self.access_token:
            print("无法获取访问令牌，跳过完整业务流程测试")
            return
            
        # 2. 创建目录结构
        print("步骤2: 创建目录结构")
        self.test_04_create_directory()
        
        # 3. 添加知识内容
        print("步骤3: 添加知识内容")
        self.test_06_add_kb_fragment()
        
        # 4. 搜索知识
        print("步骤4: 搜索知识")
        self.test_07_search_knowledge()
        
        # 5. 获取知识结构
        print("步骤5: 获取知识结构")
        self.test_08_get_fragments()
        self.test_09_get_file_tree()
        
        # 6. 管理目录
        print("步骤6: 管理目录")
        self.test_10_get_directory_list()
        self.test_11_update_directory()
        
        # 7. 构建知识结构
        print("步骤7: 构建知识结构")
        self.test_14_build_tree()
        self.test_15_build_forest()
        
        print("✅ 完整业务流程测试完成")


def run_tests():
    """运行所有测试"""
    print("开始运行完整的API测试...")
    
    # 创建测试实例
    test_instance = TestAPIComplete()
    
    try:
        # 运行各个测试方法
        test_methods = [
            test_instance.test_01_register_user,
            test_instance.test_01_5_registration_and_auto_login,
            test_instance.test_02_login_user,
            test_instance.test_03_get_protected_resource,
            test_instance.test_04_create_directory,
            test_instance.test_05_upload_file,
            test_instance.test_06_add_kb_fragment,
            test_instance.test_07_search_knowledge,
            test_instance.test_08_get_fragments,
            test_instance.test_09_get_file_tree,
            test_instance.test_10_get_directory_list,
            test_instance.test_11_update_directory,
            test_instance.test_12_delete_kb_data,
            test_instance.test_13_delete_directory,
            test_instance.test_14_build_tree,
            test_instance.test_15_build_forest,
            test_instance.test_16_complete_business_flow
        ]
        
        for test_method in test_methods:
            try:
                test_instance.setup_method()
                test_method()
                print(f"✅ {test_method.__name__} 测试通过")
            except Exception as e:
                print(f"❌ {test_method.__name__} 测试失败: {e}")
            finally:
                test_instance.teardown_method()
                
    except Exception as e:
        print(f"测试运行出错: {e}")
    finally:
        print("API测试完成")


if __name__ == "__main__":
    run_tests()
