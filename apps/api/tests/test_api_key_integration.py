"""
API Key 认证集成测试
测试API Key认证与现有系统的集成
"""
import asyncio
import json
import requests
from typing import Dict, Any


class APIKeyIntegrationTester:
    """API Key认证集成测试类"""
    
    def __init__(self, base_url: str = "http://localhost:5005/api/v1"):
        self.base_url = base_url
        self.session = requests.Session()
        self.access_token = None
        self.api_key = None
        self.test_username = "test_user_integration"
        self.test_password = "test_password_123"
        self.test_email = "test_integration@example.com"
        self.test_phone = "13800138002"
        
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
    
    def test_01_setup_user_and_api_key(self):
        """测试设置用户和API Key"""
        print("\n=== 测试设置用户和API Key ===")
        
        # 1. 注册用户
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
        print(f"用户注册响应状态码: {response.status_code}")
        
        # 2. 用户登录
        login_data = {
            "username": self.test_username,
            "password": self.test_password
        }
        
        response = self.session.post(
            f"{self.base_url}/auth/jwt/login",
            data=login_data
        )
        print(f"用户登录响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            self.access_token = response_data.get("access_token")
            print(f"获取到访问令牌: {self.access_token[:20]}...")
        
        # 3. 创建API Key
        if self.access_token:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            api_key_data = {
                "name": "集成测试API Key",
                "enabled_modules": ["all"],
                "expires_at": None
            }
            
            response = self.session.post(
                f"{self.base_url}/auth/api-key/create",
                json=api_key_data,
                headers=headers
            )
            print(f"创建API Key响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                self.api_key = response_data.get("data", {}).get("api_key")
                print(f"获取到API Key: {self.api_key[:20]}...")
        
        return self.access_token is not None and self.api_key is not None
    
    def test_02_api_key_with_jobs(self):
        """测试API Key与Job功能集成"""
        print("\n=== 测试API Key与Job功能集成 ===")
        
        if not self.api_key:
            print("没有API Key，跳过测试")
            return False
        
        headers = {"X-API-Key": self.api_key}
        
        # 1. 创建Job
        job_data = {
            "source_type": "url",
            "source_url": "https://example.com/test.pdf",
            "parsing_params": {
                "kb_dir": "API Key测试目录"
            },
            "data_id": "test_data_api_key",
            "result_mode": "auto"
        }
        
        response = self.session.post(
            f"{self.base_url}/jobs",
            json=job_data,
            headers=headers
        )
        print(f"创建Job响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            print(f"创建Job失败: {response.text}")
            return False
        
        job_response = response.json()
        job_id = job_response.get("data", {}).get("job_id")
        print(f"创建Job成功，Job ID: {job_id}")
        
        # 2. 获取Job列表
        response = self.session.get(
            f"{self.base_url}/jobs/page",
            headers=headers
        )
        print(f"获取Job列表响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            print(f"获取Job列表失败: {response.text}")
            return False
        
        # 3. 获取Job状态
        if job_id:
            response = self.session.get(
                f"{self.base_url}/jobs/{job_id}",
                headers=headers
            )
            print(f"获取Job状态响应状态码: {response.status_code}")
            
            if response.status_code != 200:
                print(f"获取Job状态失败: {response.text}")
                return False
        
        return True
    
    def test_03_api_key_with_file_upload(self):
        """测试API Key与文件上传功能集成"""
        print("\n=== 测试API Key与文件上传功能集成 ===")
        
        if not self.api_key:
            print("没有API Key，跳过测试")
            return False
        
        headers = {"X-API-Key": self.api_key}
        
        # 创建测试文件
        test_content = "这是一个通过API Key认证上传的测试文件。"
        files = {
            'file': ('test_api_key.txt', test_content, 'text/plain')
        }
        
        response = self.session.post(
            f"{self.base_url}/kb/upload_file",
            files=files,
            headers=headers
        )
        
        print(f"文件上传响应状态码: {response.status_code}")
        try:
            response_data = response.json()
            print(f"文件上传响应内容: {response_data}")
            return response.status_code == 200
        except Exception as e:
            print(f"文件上传响应解析失败: {e}")
            return False
    
    def test_04_api_key_with_queue_management(self):
        """测试API Key与队列管理功能集成"""
        print("\n=== 测试API Key与队列管理功能集成 ===")
        
        if not self.api_key:
            print("没有API Key，跳过测试")
            return False
        
        headers = {"X-API-Key": self.api_key}
        
        # 获取队列状态
        response = self.session.get(
            f"{self.base_url}/queue/status",
            headers=headers
        )
        
        print(f"获取队列状态响应状态码: {response.status_code}")
        try:
            response_data = response.json()
            print(f"获取队列状态响应内容: {response_data}")
            return response.status_code == 200
        except Exception as e:
            print(f"获取队列状态响应解析失败: {e}")
            return False
    
    def test_05_api_key_with_redis_demo(self):
        """测试API Key与Redis演示功能集成"""
        print("\n=== 测试API Key与Redis演示功能集成 ===")
        
        if not self.api_key:
            print("没有API Key，跳过测试")
            return False
        
        headers = {"X-API-Key": self.api_key}
        
        # 获取Redis信息
        response = self.session.get(
            f"{self.base_url}/redis/info",
            headers=headers
        )
        
        print(f"获取Redis信息响应状态码: {response.status_code}")
        try:
            response_data = response.json()
            print(f"获取Redis信息响应内容: {response_data}")
            return response.status_code == 200
        except Exception as e:
            print(f"获取Redis信息响应解析失败: {e}")
            return False
    
    def test_06_api_key_performance_test(self):
        """测试API Key认证性能"""
        print("\n=== 测试API Key认证性能 ===")
        
        if not self.api_key:
            print("没有API Key，跳过测试")
            return False
        
        headers = {"X-API-Key": self.api_key}
        
        # 进行多次请求测试性能
        import time
        start_time = time.time()
        
        success_count = 0
        total_requests = 10
        
        for i in range(total_requests):
            response = self.session.get(
                f"{self.base_url}/auth/me",
                headers=headers
            )
            if response.status_code == 200:
                success_count += 1
        
        end_time = time.time()
        total_time = end_time - start_time
        avg_time = total_time / total_requests
        
        print(f"总请求数: {total_requests}")
        print(f"成功请求数: {success_count}")
        print(f"总时间: {total_time:.2f}秒")
        print(f"平均响应时间: {avg_time:.2f}秒")
        
        return success_count == total_requests
    
    def test_07_api_key_concurrent_test(self):
        """测试API Key并发认证"""
        print("\n=== 测试API Key并发认证 ===")
        
        if not self.api_key:
            print("没有API Key，跳过测试")
            return False
        
        import threading
        import time
        
        results = []
        
        def make_request():
            headers = {"X-API-Key": self.api_key}
            response = self.session.get(
                f"{self.base_url}/auth/me",
                headers=headers
            )
            results.append(response.status_code == 200)
        
        # 创建多个线程并发请求
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        success_count = sum(results)
        total_requests = len(results)
        
        print(f"并发请求数: {total_requests}")
        print(f"成功请求数: {success_count}")
        
        return success_count == total_requests
    
    def test_08_api_key_error_handling(self):
        """测试API Key错误处理"""
        print("\n=== 测试API Key错误处理 ===")
        
        # 测试各种错误情况
        error_cases = [
            ("无效API Key", "dummy-api-key-for-tests"),
            ("空API Key", ""),
            ("过期API Key", "expired_api_key_12345"),
            ("格式错误的API Key", "wrong_format_key"),
        ]
        
        success_count = 0
        
        for case_name, api_key in error_cases:
            headers = {"X-API-Key": api_key} if api_key else {}
            
            response = self.session.get(
                f"{self.base_url}/auth/me",
                headers=headers
            )
            
            print(f"{case_name}响应状态码: {response.status_code}")
            
            # 期望返回401未授权
            if response.status_code == 401:
                success_count += 1
        
        return success_count == len(error_cases)
    
    def test_09_api_key_non_job_access_denied(self):
        """测试API Key访问非Job接口被拒绝"""
        print("\n=== 测试API Key访问非Job接口被拒绝 ===")
        
        if not self.api_key:
            print("没有API Key，跳过测试")
            return False
        
        headers = {"X-API-Key": self.api_key}
        
        # 测试访问非Job接口
        non_job_endpoints = [
            ("知识库接口", "/kb/search_kb", "POST"),
            ("用户管理接口", "/user/profile", "GET"),
            ("计费接口", "/billing/credits", "GET"),
        ]
        
        success_count = 0
        
        for endpoint_name, endpoint_path, method in non_job_endpoints:
            if method == "GET":
                response = self.session.get(f"{self.base_url}{endpoint_path}", headers=headers)
            elif method == "POST":
                response = self.session.post(f"{self.base_url}{endpoint_path}", json={}, headers=headers)
            
            print(f"{endpoint_name}响应状态码: {response.status_code}")
            
            # 期望返回401未授权（因为API Key只能访问Job接口）
            if response.status_code == 401:
                success_count += 1
                print(f"✅ {endpoint_name}正确返回401")
            else:
                print(f"❌ {endpoint_name}返回了错误的状态码: {response.status_code}")
        
        return success_count == len(non_job_endpoints)
    
    def run_all_tests(self):
        """运行所有集成测试"""
        print("开始运行API Key认证集成测试...")
        print("=" * 70)
        
        test_results = []
        
        # 运行各个测试
        tests = [
            ("设置用户和API Key", self.test_01_setup_user_and_api_key),
            ("API Key与Job功能集成", self.test_02_api_key_with_jobs),
            ("API Key与文件上传功能集成", self.test_03_api_key_with_file_upload),
            ("API Key与队列管理功能集成", self.test_04_api_key_with_queue_management),
            ("API Key与Redis演示功能集成", self.test_05_api_key_with_redis_demo),
            ("API Key认证性能测试", self.test_06_api_key_performance_test),
            ("API Key并发认证测试", self.test_07_api_key_concurrent_test),
            ("API Key错误处理测试", self.test_08_api_key_error_handling),
            ("API Key访问非Job接口被拒绝", self.test_09_api_key_non_job_access_denied),
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
        print("\n" + "=" * 70)
        print("API Key认证集成测试结果摘要:")
        passed = sum(1 for _, result in test_results if result)
        total = len(test_results)
        
        for test_name, result in test_results:
            status = "✅ 通过" if result else "❌ 失败"
            print(f"  {test_name}: {status}")
        
        print(f"\n总计: {passed}/{total} 个测试通过")
        
        if passed == total:
            print("🎉 所有API Key认证集成测试都通过了！")
        else:
            print("⚠️ 部分测试失败，请检查API服务是否正常运行")
        
        return passed == total


def main():
    """主函数"""
    tester = APIKeyIntegrationTester()
    success = tester.run_all_tests()
    return success


if __name__ == "__main__":
    main()
