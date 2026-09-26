#include <windows.h> 
#include <iostream>
using namespace std;
int main() {
	SetConsoleTitle("即将开始...");
	printf("人机验证后将开始下载Windows10介质创建&系统升级器(原版MediaCreationTool版本21H2,后续下载可能提示要更新.)");
	Sleep(3999);
	system("captcha.exe");
	system("color");
	system("cls"); 
	SetConsoleTitle("正在下载...");
	system("color");
	system("curl https://download.microsoft.com/download/b/0/5/b053c6bc-fc07-4785-a66a-63c5aeb715a9/MediaCreationTool21H2.exe -o MediaCreationTool21H2.exe --progress");
	printf("完成,文件名为MediaCreationTool21H2.exe,在该程序同目录.");
	system("pause"); 
	return 0;
}
