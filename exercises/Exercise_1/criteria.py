from checks import call, criterion, program

TITLE = "Gestão de notas"

# Answers given to input() when the file is loaded to collect its functions.
# "fim" ends the grade loop right away.
LOAD_INPUTS = ["fim"]

# Words from a hidden instruction in the assignment. A hit only shows a
# warning to the teacher. Remove the line if the assignment has none.
AI_TRAP = ["nota_secreta"]

CRITERIA = [
    criterion("media", 4, [
        call("media", [10, 12, 14]),
        call("media", [15]),
        call("media", [], hint="Uma lista vazia tem média 0."),
    ], description="Devolve a média das notas, ou 0 se a lista é vazia."),

    criterion("classificar", 4, [
        call("classificar", 15),
        call("classificar", 10, hint="10 já é aprovado (>= 10)."),
        call("classificar", 9.5),
        call("classificar", -1, hint="Fora de [0, 20] é inválida."),
        call("classificar", 21, hint="Fora de [0, 20] é inválida."),
    ], description="Aprovado, Reprovado ou Inválida."),

    criterion("contar_aprovados", 3, [
        call("contar_aprovados", [8, 10, 12, 19]),
        call("contar_aprovados", []),
        call("contar_aprovados", [9.9, 3]),
    ], description="Conta as notas >= 10."),

    criterion("subir_notas", 3, [
        call("subir_notas", [10, 12], 2, check_return=False, mutates=[0],
             hint="A função altera a lista recebida, não cria outra."),
        call("subir_notas", [18, 20], 5, check_return=False, mutates=[0],
             hint="Nenhuma nota passa de 20."),
    ], description="Soma o bónus a cada nota, com máximo de 20."),

    criterion("mostrar_resultado", 2, [
        call("mostrar_resultado", "Ana", 15, check_return=False,
             output="equal"),
        call("mostrar_resultado", "Rui", 8, check_return=False,
             output="equal"),
    ], description="Imprime o nome, a nota e a classificação."),

    criterion("Programa", 4, [
        program(["12", "8", "fim"], contains=["Média: 10.0", "Aprovados: 1"],
                label="programa: notas 12 e 8"),
        program(["fim"], contains=["Média: 0.0", "Aprovados: 0"],
                label="programa: sem notas"),
    ], description="Lê notas até 'fim' e mostra a média e os aprovados."),
]
