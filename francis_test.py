import pandas as pd

path = r"C:\Users\steffan.thomas\Downloads\Untitled 31_2026-02-10-1646 (1).csv"

utf_8_df = pd.read_csv(path, encoding='utf-8')
utf_8_sig_df = pd.read_csv(path, encoding='utf-8-sig')
regular_df = pd.read_csv(path)

print("UTF-8 Encoding:", utf_8_df.head(10))
# print("UTF-8-SIG Encoding:", utf_8_sig_df.head(10)) 
print("Regular Encoding:", regular_df.head(10))



