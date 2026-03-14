def crea_tavola():
    return [[" " for _ in range(3)] for _ in range(3)]


def stampa_tavola(tavola):
    print()
    for i, riga in enumerate(tavola):
        print(" | ".join(riga))
        if i < 2:
            print("---------")
    print()


def controlla_vincitore(tavola, giocatore):
    # Righe e colonne
    for i in range(3):
        if all(tavola[i][j] == giocatore for j in range(3)):
            return True
        if all(tavola[j][i] == giocatore for j in range(3)):
            return True
    # Diagonali
    if all(tavola[i][i] == giocatore for i in range(3)):
        return True
    if all(tavola[i][2 - i] == giocatore for i in range(3)):
        return True
    return False


def tavola_piena(tavola):
    return all(tavola[i][j] != " " for i in range(3) for j in range(3))


def ottieni_mossa(tavola, giocatore):
    while True:
        try:
            mossa = input(f"Giocatore {giocatore}, inserisci la tua mossa (riga colonna, es: 1 2): ")
            riga, col = map(int, mossa.split())
            if not (1 <= riga <= 3 and 1 <= col <= 3):
                print("Inserisci valori tra 1 e 3.")
                continue
            riga -= 1
            col -= 1
            if tavola[riga][col] != " ":
                print("Quella cella è già occupata. Scegli un'altra.")
                continue
            return riga, col
        except (ValueError, IndexError):
            print("Input non valido. Inserisci due numeri separati da spazio (es: 1 2).")


def gioca():
    tavola = crea_tavola()
    giocatori = ["X", "O"]
    turno = 0

    print("=== GIOCO DEL TRIS ===")
    print("Inserisci la mossa come: riga colonna (es: 1 2)")

    while True:
        giocatore = giocatori[turno % 2]
        stampa_tavola(tavola)
        riga, col = ottieni_mossa(tavola, giocatore)
        tavola[riga][col] = giocatore

        if controlla_vincitore(tavola, giocatore):
            stampa_tavola(tavola)
            print(f"Giocatore {giocatore} ha vinto! Complimenti!")
            break

        if tavola_piena(tavola):
            stampa_tavola(tavola)
            print("Pareggio! La tavola è piena.")
            break

        turno += 1

    risposta = input("Vuoi giocare ancora? (s/n): ").strip().lower()
    if risposta == "s":
        gioca()


if __name__ == "__main__":
    gioca()
