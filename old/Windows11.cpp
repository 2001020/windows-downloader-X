#include <windows.h> 
#include <iostream>
using namespace std;
int main() {
	SetConsoleTitle("即将开始...");
	printf("人机验证后将开始下载Windows11介质创建器(原版MediaCreationTool)");
	Sleep(1999);
	system("captcha.exe");
	system("color");
	system("cls"); 
	SetConsoleTitle("正在下载...");
	system("curl https://software-static.download.prss.microsoft.com/pr/download/888969d5-f34g-4e03-ac9d-1f9786c69161/MediaCreationToolW11.exe -o MediaCreationToolW11.exe --progress");
	printf("完成,文件名为MediaCreationToolW11.exe,在该程序同目录.");
	system("pause"); 
	return 0;
}
