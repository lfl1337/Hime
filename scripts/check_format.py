with open(r'C:\Projekte\Hime\data\raw_jparacrawl\extracted\en-ja\en-ja.bicleaner05.txt', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        print(f"Zeile {i+1}: {repr(line)}")
        if i >= 4:
            break
