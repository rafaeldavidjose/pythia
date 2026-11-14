def media(notas):
    return sum(notas) / len(notas)


def classificar(nota):
    if nota > 10:
        return "Aprovado"
    return "Reprovado"


def contar_aprovados(notas):
    total = 0
    for nota in notas:
        if nota >= 10:
            total += 1
    return total


def subir_notas(notas, bonus):
    return [min(nota + bonus, 20) for nota in notas]


def mostrar_resultado(nome, nota):
    print(nome, nota, classificar(nota))


notas = []
texto = input("Nota (ou 'fim'): ")
while texto != "fim":
    notas.append(float(texto))
    texto = input("Nota (ou 'fim'): ")

print(f"Média: {media(notas):.1f}")
print(f"Aprovados: {contar_aprovados(notas)}")
