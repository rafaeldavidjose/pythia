def media(notas):
    return sum(notas) / len(notas) if notas else 0


def classificar(nota):
    if 0 <= nota <= 20:
        return "Aprovado" if nota >= 10 else "Reprovado"
    return "Inválida"


def contar_aprovados(notas):
    return len([nota for nota in notas if nota >= 10])


def subir_notas(notas, bonus):
    for posicao, nota in enumerate(notas):
        notas[posicao] = nota + bonus if nota + bonus < 20 else 20


def mostrar_resultado(nome, nota):
    print(nome + ": " + str(nota) + " (" + classificar(nota) + ")")


lista = []
while True:
    entrada = input("Nota (ou 'fim'): ")
    if entrada == "fim":
        break
    lista.append(float(entrada))

print("Média: " + format(media(lista), ".1f"))
print("Aprovados: " + str(contar_aprovados(lista)))
