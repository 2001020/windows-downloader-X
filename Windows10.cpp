#include <windows.h> 
#include <iostream>
using namespace std;
int main() {
	SetConsoleTitle("������ʼ...");
	printf("�˻���֤�󽫿�ʼ����Windows10���ʴ���&ϵͳ������(ԭ��MediaCreationTool�汾21H2,�������ؿ�����ʾҪ����.)");
	Sleep(3999);
	system("captcha.exe");
	system("color");
	system("cls"); 
	SetConsoleTitle("��������...");
	system("color");
	system("curl https://download.microsoft.com/download/b/0/5/b053c6bc-fc07-4785-a66a-63c5aeb715a9/MediaCreationTool21H2.exe -o MediaCreationTool21H2.exe --progress");
	printf("���,�ļ���ΪMediaCreationTool21H2.exe,�ڸó���ͬĿ¼.");
	system("pause"); 
	return 0;
}
