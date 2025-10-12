"""
API Key 认证测试
"""
import asyncio
import json
import requests
from typing import Dict, Any


class APIKeyAuthTester:
    """API Key认证测试类"""
    
    def __init__(self, base_url: str = "http://localhost:5005/api/v1"):
        self.base_url = base_url
        self.session = requests.Session()
        self.access_token = None
        self.api_key = None
        self.test_username = "test_user_api_key"
        self.test_password = "test_password_123"
        self.test_email = "test_api_key@example.com"
        self.test_phone = "13800138001"
        
    def setup_method(self):
        """测试前的设置"""
        self.session = requests.Session()
        self.access_token = None
        self.api_key = None
        
    def teardown_method(self):
        """测试后的清理"""
        # 清理测试数据
        if self.api_key:
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
        return response.status_code in [200, 400, 422]
    
    def test_02_login_user(self):
        """测试用户登录"""
        print("\n=== 测试用户登录 ===")
        
        login_data = {
            "username": self.test_username,
            "password": self.test_password
        }
        
        response = self.session.post(
            f"{self.base_url}/auth/jwt/login",
            data=login_data
        )
        
        print(f"登录响应状态码: {response.status_code}")
        try:
            response_data = response.json()
            print(f"登录响应内容: {response_data}")
            
            if response.status_code == 200:
                self.access_token = response_data.get("access_token")
                print(f"获取到访问令牌: {self.access_token[:20]}...")
                return True
            else:
                print("登录失败")
                return False
        except Exception as e:
            print(f"登录响应解析失败: {e}")
            return False
    
    def test_03_create_api_key(self):
        """测试创建API Key"""
        print("\n=== 测试创建API Key ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return False
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        api_key_data = {
            "name": "测试API Key",
            "enabled_modules": ["all"],
            "expires_at": None
        }
        
        response = self.session.post(
            f"{self.base_url}/auth/api-key/create",
            json=api_key_data,
            headers=headers
        )
        
        print(f"创建API Key响应状态码: {response.status_code}")
        try:
            response_data = response.json()
            print(f"创建API Key响应内容: {response_data}")
            
            if response.status_code == 200:
                self.api_key = response_data.get("data", {}).get("api_key")
                print(f"获取到API Key: {self.api_key[:20]}...")
                return True
            else:
                print("创建API Key失败")
                return False
        except Exception as e:
            print(f"创建API Key响应解析失败: {e}")
            return False
    
    def test_04_list_api_keys(self):
        """测试获取API Key列表"""
        print("\n=== 测试获取API Key列表 ===")
        
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return False
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        response = self.session.get(
            f"{self.base_url}/auth/api-key/list",
            headers=headers
        )
        
        print(f"获取API Key列表响应状态码: {response.status_code}")
        try:
            response_data = response.json()
            print(f"获取API Key列表响应内容: {response_data}")
            return response.status_code == 200
        except Exception as e:
            print(f"获取API Key列表响应解析失败: {e}")
            return False
    
    def test_05_api_key_auth_protected_endpoint(self):
        """测试使用API Key访问受保护的端点"""
        print("\n=== 测试API Key认证访问受保护端点 ===")
        
        if not self.api_key:
            print("没有API Key，跳过测试")
            return False
        
        headers = {"X-API-Key": self.api_key}
        
        # 测试访问用户信息端点
        response = self.session.get(
            f"{self.base_url}/auth/me",
            headers=headers
        )
        
        print(f"API Key认证访问用户信息响应状态码: {response.status_code}")
        try:
            response_data = response.json()
            print(f"API Key认证访问用户信息响应内容: {response_data}")
            return response.status_code == 200
        except Exception as e:
            print(f"API Key认证访问用户信息响应解析失败: {e}")
            return False
    
    def test_06_api_key_auth_kb_endpoint(self):
        """测试使用API Key访问知识库端点"""
        print("\n=== 测试API Key认证访问知识库端点 ===")
        
        if not self.api_key:
            print("没有API Key，跳过测试")
            return False
        
        headers = {"X-API-Key": self.api_key}
        
        # 测试访问知识库端点
        kb_data = {
            "kb_path": "测试目录",
            "fragment_content": "这是一个通过API Key认证添加的知识碎片。",
            "fragment_title": "API Key测试知识碎片",
            "smart_title_parse": True,
            "summary_image": False,
            "summary_txt": True,
            "summary_table": False,
            "add_frag_desc": "API Key测试描述",
            "label": "API Key测试标签"
        }
        
        response = self.session.post(
            f"{self.base_url}/kb/add_kb_fragment",
            json=kb_data,
            headers=headers
        )
        
        print(f"API Key认证访问知识库端点响应状态码: {response.status_code}")
        try:
            response_data = response.json()
            print(f"API Key认证访问知识库端点响应内容: {response_data}")
            return response.status_code == 200
        except Exception as e:
            print(f"API Key认证访问知识库端点响应解析失败: {e}")
            return False
    
    def test_07_invalid_api_key(self):
        """测试无效API Key"""
        print("\n=== 测试无效API Key ===")
        
        headers = {"X-API-Key": "dummy-api-key-for-tests"}
        
        response = self.session.get(
            f"{self.base_url}/auth/me",
            headers=headers
        )
        
        print(f"无效API Key响应状态码: {response.status_code}")
        try:
            response_data = response.json()
            print(f"无效API Key响应内容: {response_data}")
            return response.status_code == 401
        except Exception as e:
            print(f"无效API Key响应解析失败: {e}")
            return False
    
    def test_08_missing_api_key(self):
        """测试缺少API Key"""
        print("\n=== 测试缺少API Key ===")
        
        # 不设置X-API-Key头部
        response = self.session.get(f"{self.base_url}/auth/me")
        
        print(f"缺少API Key响应状态码: {response.status_code}")
        try:
            response_data = response.json()
            print(f"缺少API Key响应内容: {response_data}")
            return response.status_code == 401
        except Exception as e:
            print(f"缺少API Key响应解析失败: {e}")
            return False
    
    def test_09_jwt_vs_api_key_auth(self):
        """测试JWT和API Key双重认证"""
        print("\n=== 测试JWT和API Key双重认证 ===")
        
        if not self.access_token or not self.api_key:
            print("缺少认证信息，跳过测试")
            return False
        
        # 测试JWT认证
        jwt_headers = {"Authorization": f"Bearer {self.access_token}"}
        jwt_response = self.session.get(
            f"{self.base_url}/auth/me",
            headers=jwt_headers
        )
        
        # 测试API Key认证
        api_key_headers = {"X-API-Key": self.api_key}
        api_key_response = self.session.get(
            f"{self.base_url}/auth/me",
            headers=api_key_headers
        )
        
        print(f"JWT认证响应状态码: {jwt_response.status_code}")
        print(f"API Key认证响应状态码: {api_key_response.status_code}")
        
        return jwt_response.status_code == 200 and api_key_response.status_code == 200
    
    def test_10_api_key_permissions(self):
        """测试API Key权限控制"""
        print("\n=== 测试API Key权限控制 ===")
        
        if not self.api_key:
            print("没有API Key，跳过测试")
            return False
        
        headers = {"X-API-Key": self.api_key}
        
        # 测试访问需要特定权限的端点
        response = self.session.get(
            f"{self.base_url}/auth/api-key/list",
            headers=headers
        )
        
        print(f"API Key权限控制响应状态码: {response.status_code}")
        try:
            response_data = response.json()
            print(f"API Key权限控制响应内容: {response_data}")
            return response.status_code == 200
        except Exception as e:
            print(f"API Key权限控制响应解析失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("开始运行API Key认证测试...")
        print("=" * 60)
        
        test_results = []
        
        # 运行各个测试
        tests = [
            ("用户注册", self.test_01_register_user),
            ("用户登录", self.test_02_login_user),
            ("创建API Key", self.test_03_create_api_key),
            ("获取API Key列表", self.test_04_list_api_keys),
            ("API Key认证访问受保护端点", self.test_05_api_key_auth_protected_endpoint),
            ("API Key认证访问知识库端点", self.test_06_api_key_auth_kb_endpoint),
            ("无效API Key", self.test_07_invalid_api_key),
            ("缺少API Key", self.test_08_missing_api_key),
            ("JWT和API Key双重认证", self.test_09_jwt_vs_api_key_auth),
            ("API Key权限控制", self.test_10_api_key_permissions),
        ]
        
        for test_name, test_func in tests:
            print(f"\n正在测试: {test_name}")
            try:
                self.setup_method()
                result = test_func()
                test_results.append((test_name, result))
                status = "✅ 通过" if result else "❌ 失败"
                print(f"{test_name}: {status}")
            except Exception as e:
                print(f"{test_name}: ❌ 异常 - {e}")
                test_results.append((test_name, False))
            finally:
                self.teardown_method()
        
        # 输出测试结果摘要
        print("\n" + "=" * 60)
        print("API Key认证测试结果摘要:")
        passed = sum(1 for _, result in test_results if result)
        total = len(test_results)
        
        for test_name, result in test_results:
            status = "✅ 通过" if result else "❌ 失败"
            print(f"  {test_name}: {status}")
        
        print(f"\n总计: {passed}/{total} 个测试通过")
        
        if passed == total:
            print("🎉 所有API Key认证测试都通过了！")
        else:
            print("⚠️ 部分测试失败，请检查API服务是否正常运行")
        
        return passed == total


def main():
    """主函数"""
    tester = APIKeyAuthTester()
    success = tester.run_all_tests()
    return success


if __name__ == "__main__":
    main()
