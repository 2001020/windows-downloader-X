#include <windows.h> 
#include <iostream>
using namespace std;
int main() {
	SetConsoleTitle("������ʼ...");
	printf("�˻���֤�󽫿�ʼ����Windows11���ʴ�����(ԭ��MediaCreationTool)");
	Sleep(1999);
	system("captcha.exe");
	system("color");
	system("cls"); 
	SetConsoleTitle("��������...");
	system("curl https://software-static.download.prss.microsoft.com/pr/download/888969d5-f34g-4e03-ac9d-1f9786c69161/MediaCreationToolW11.exe -o MediaCreationToolW11.exe --progress");
	printf("���,�ļ���ΪMediaCreationToolW11.exe,�ڸó���ͬĿ¼.");
	system("pause"); 
	return 0;
}
