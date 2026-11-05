"""Execute depois de compilar, na localização definitiva da pasta dist."""

from pathlib import Path
import os


def main():
    raiz = Path(__file__).resolve().parents[1]
    pasta = raiz / "dist" / "FalciformeExplicavel"
    executavel = pasta / "FalciformeExplicavel"
    if not executavel.is_file():
        raise SystemExit("Gere o aplicativo antes de instalar o atalho.")
    # Escape da gramática Exec do freedesktop, incluindo expansão de códigos %.
    destino = str(executavel).replace("%", "%%")
    for caractere in ("\\", '"', "`", "$"):
        destino = destino.replace(caractere, "\\" + caractere)
    icone = pasta / "_internal" / "assets" / "icone.png"
    conteudo = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Falciforme Explicável\n"
        "Comment=Acompanhamento longitudinal para avaliação médica\n"
        f'Exec="{destino}"\n'
        f"Icon={icone}\n"
        "Terminal=false\n"
        "Categories=Education;Science;\n"
    )
    dados = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    atalho = dados / "applications" / "falciforme-explicavel.desktop"
    atalho.parent.mkdir(parents=True, exist_ok=True)
    atalho.write_text(conteudo, encoding="utf-8")
    atalho.chmod(0o755)
    print(f"Atalho criado no menu de aplicativos: {atalho}")


if __name__ == "__main__":
    main()
