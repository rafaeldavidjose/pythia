def media(notas):
    if len(notas) == 0:
        return 0
    return sum(notas) / len(notas)


def classificar(nota):
    if nota < 0 or nota > 20:
        return "Inválida"
    if nota >= 10:
        return "Aprovado"
    return "Reprovado"


def contar_aprovados(notas):
    total = 0
    posicao = 0
    while posicao < len(notas):
        if notas[posicao] >= 10:
            total += 1
    return total


def subir_notas(notas, bonus):
    for posicao in range(len(notas)):
        notas[posicao] = min(notas[posicao] + bonus, 20)


def mostrar_resultado(nome, nota):
    print(f"{nome}: {nota} ({classificar(nota)})")


notas = []
texto = input("Nota (ou 'fim'): ")
while texto != "fim":
    notas.append(float(texto))
    texto = input("Nota (ou 'fim'): ")

print(f"Média: {media(notas):.1f}")
print(f"Aprovados: {contar_aprovados(notas)}")
