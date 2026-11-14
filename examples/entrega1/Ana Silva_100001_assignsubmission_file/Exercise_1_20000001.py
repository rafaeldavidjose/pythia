# Exemplo: gestão de notas
# Funções, listas e ciclos

# Média das notas (0 se a lista estiver vazia)
def media(notas):
    if len(notas) == 0:
        return 0
    return sum(notas) / len(notas)


# "Aprovado" se a nota for >= 10, "Reprovado" se for < 10
# e "Inválida" se estiver fora de [0, 20]
def classificar(nota):
    if nota < 0 or nota > 20:
        return "Inválida"
    if nota >= 10:
        return "Aprovado"
    return "Reprovado"


# Número de notas >= 10
def contar_aprovados(notas):
    total = 0
    for nota in notas:
        if nota >= 10:
            total += 1
    return total


# Soma bonus a cada nota da lista (altera a lista), sem passar de 20
def subir_notas(notas, bonus):
    for i in range(len(notas)):
        notas[i] = min(notas[i] + bonus, 20)


# Imprime, por exemplo: Ana: 15 (Aprovado)
def mostrar_resultado(nome, nota):
    print(f"{nome}: {nota} ({classificar(nota)})")


notas = []
texto = input("Nota (ou 'fim'): ")
while texto != "fim":
    notas.append(float(texto))
    texto = input("Nota (ou 'fim'): ")

print(f"Média: {media(notas):.1f}")
print(f"Aprovados: {contar_aprovados(notas)}")
