int main() {
    char* msg = "ALMIDO alive\n";
    int i = 0;
    while (msg[i]) {
        write(1, &msg[i], 1);
        i++;
    }
    return 0;
}
