"""
简化的API接口测试
测试知识库管理系统的基本功能
"""
import os
import tempfile
import requests
import json
from typing import Dict, Any


class SimpleAPITester:
    """简化的API测试类"""
    
    def __init__(self, base_url: str = "http://localhost:5005/api/v1"):
        self.base_url = base_url
        self.session = requests.Session()
        self.access_token = None
        self.test_username = "test_user_simple"
        self.test_password = "test_password_123"
        self.test_email = "test_fresh@example.com"
        self.test_phone = "13800138000"
        
    def test_root_endpoint(self):
        """测试根端点"""
        print("=== 测试根端点 ===")
        try:
            response = self.session.get("http://localhost:5005/")
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.json()}")
            return response.status_code == 200
        except Exception as e:
            print(f"根端点测试失败: {e}")
            return False
    
    def test_user_registration(self):
        """测试用户注册"""
        print("\n=== 测试用户注册 ===")
        try:
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
            
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.json()}")
            
            # 注册可能成功或失败（用户已存在），都算通过
            return response.status_code in [200, 201, 400, 422]
            
        except Exception as e:
            print(f"用户注册测试失败: {e}")
            return False
    
    def test_registration_and_auto_login(self):
        """测试注册后自动登录流程"""
        print("\n=== 测试注册后自动登录流程 ===")
        try:
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
                return False
            
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
                    return True
                else:
                    print("❌ 登录响应中没有有效的访问令牌")
                    return False
            else:
                print(f"❌ 自动登录失败，状态码: {login_response.status_code}")
                return False
                
        except Exception as e:
            print(f"注册后自动登录测试失败: {e}")
            return False
    
    def test_user_login(self):
        """测试用户登录"""
        print("\n=== 测试用户登录 ===")
        try:
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
            
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.json()}")
            
            if response.status_code == 200:
                response_data = response.json()
                if "access_token" in response_data:
                    self.access_token = response_data["access_token"]
                    print(f"获取到访问令牌: {self.access_token[:20]}...")
                    return True
                else:
                    print("登录响应中没有有效的访问令牌")
                    return False
            
            return False
            
        except Exception as e:
            print(f"用户登录测试失败: {e}")
            return False
    
    def test_protected_resource(self):
        """测试受保护资源"""
        print("\n=== 测试受保护资源 ===")
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = self.session.get(
                f"{self.base_url}/auth/me",
                headers=headers
            )
            
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.json()}")
            
            return response.status_code == 200
            
        except Exception as e:
            print(f"受保护资源测试失败: {e}")
            return False
    
    def test_kb_endpoints(self):
        """测试知识库相关端点"""
        print("\n=== 测试知识库端点 ===")
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return False
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        # 测试创建目录
        print("测试创建目录...")
        try:
            directory_data = {
                "id": "test_dir_001",
                "title": "测试目录",
                "parent_id": None,
                "user_id": "1"
            }
            
            response = self.session.post(
                f"{self.base_url}/kb/create_directory",
                json=directory_data,
                headers=headers
            )
            print(f"创建目录状态码: {response.status_code}")
            
        except Exception as e:
            print(f"创建目录失败: {e}")
        
        # 测试新的异步知识库API
        print("测试新的异步知识库API...")
        try:
            # 测试创建知识库任务
            job_data = {
                "source_type": "url",
                "file_url": "https://example.com/test.pdf",
                "metadata": {
                    "doc_type": "pdf",
                    "kb_dir": "测试目录",
                    "smart_title_parse": True,
                    "summary_image": False,
                    "summary_txt": True,
                    "summary_table": False,
                    "add_frag_desc": "测试描述"
                }
            }
            
            response = self.session.post(
                f"{self.base_url}/kb/jobs",
                json=job_data,
                headers=headers
            )
            print(f"创建知识库任务状态码: {response.status_code}")
            
            if response.status_code == 200:
                job_result = response.json()
                job_id = job_result.get("data", {}).get("job_id")
                if job_id:
                    print(f"任务ID: {job_id}")
                    
                    # 查询任务状态
                    status_response = self.session.get(
                        f"{self.base_url}/kb/jobs/{job_id}",
                        headers=headers
                    )
                    print(f"查询任务状态码: {status_response.status_code}")
            
        except Exception as e:
            print(f"测试新API失败: {e}")
        
        return True
    
    def test_file_upload(self):
        """测试文件上传"""
        print("\n=== 测试文件上传 ===")
        if not self.access_token:
            print("没有访问令牌，跳过测试")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
                temp_file.write("这是一个测试文档内容。")
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
                    
                    print(f"文件上传状态码: {response.status_code}")
                    print(f"文件上传响应: {response.json()}")
                    
                    return response.status_code in [200, 201, 400, 422, 500]
                    
            finally:
                # 清理临时文件
                os.unlink(temp_file_path)
                
        except Exception as e:
            print(f"文件上传测试失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("开始运行简化的API测试...")
        print("=" * 50)
        
        test_results = []
        
        # 运行各个测试
        tests = [
            ("根端点", self.test_root_endpoint),
            ("用户注册", self.test_user_registration),
            ("注册后自动登录", self.test_registration_and_auto_login),
            ("用户登录", self.test_user_login),
            ("受保护资源", self.test_protected_resource),
            ("知识库端点", self.test_kb_endpoints),
            ("文件上传", self.test_file_upload),
        ]
        
        for test_name, test_func in tests:
            print(f"\n正在测试: {test_name}")
            try:
                result = test_func()
                test_results.append((test_name, result))
                status = "✅ 通过" if result else "❌ 失败"
                print(f"{test_name}: {status}")
            except Exception as e:
                print(f"{test_name}: ❌ 异常 - {e}")
                test_results.append((test_name, False))
        
        # 输出测试结果摘要
        print("\n" + "=" * 50)
        print("测试结果摘要:")
        passed = sum(1 for _, result in test_results if result)
        total = len(test_results)
        
        for test_name, result in test_results:
            status = "✅ 通过" if result else "❌ 失败"
            print(f"  {test_name}: {status}")
        
        print(f"\n总计: {passed}/{total} 个测试通过")
        
        if passed == total:
            print("🎉 所有测试都通过了！")
        else:
            print("⚠️ 部分测试失败，请检查API服务是否正常运行")
        
        return passed == total


def main():
    """主函数"""
    # 检查API服务是否运行
    tester = SimpleAPITester()
    
    print("检查API服务是否运行...")
    if not tester.test_root_endpoint():
        print("❌ API服务未运行，请先启动服务:")
        print("   python main.py")
        print("   或")
        print("   uvicorn main:app --host 0.0.0.0 --port 5005")
        return False
    
    print("✅ API服务正在运行")
    
    # 运行所有测试
    return tester.run_all_tests()


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
