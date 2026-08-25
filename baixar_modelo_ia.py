"""
Baixa o arquivo de modelo de IA usado na Avaliação Postural automática
(detecção de pontos do corpo/postura nas fotos).

Isso só precisa ser rodado UMA VEZ, no computador/servidor onde o site vai
rodar. Sem esse arquivo, o botão "Detectar automaticamente" sempre mostra
a mensagem de que a IA não está instalada.

Como usar (dentro da pasta webapp_v2, com o Python que você já usa pra
rodar o site):

    python baixar_modelo_ia.py

Ao terminar, reinicie o site (pare com Ctrl+C e rode "python app.py" de
novo). O botão de detecção automática passa a funcionar.
"""
import os
import sys
import urllib.request

DESTINO = os.path.join(os.path.dirname(__file__), "instance", "models", "pose_landmarker.task")

# Se este link parar de funcionar no futuro, procure por
# "mediapipe pose landmarker task file download" no Google — é um arquivo
# oficial e gratuito do Google/MediaPipe.
URLS = [
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task",
]


def baixar():
    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)

    if os.path.exists(DESTINO) and os.path.getsize(DESTINO) > 1_000_000:
        print(f"Modelo já está instalado em: {DESTINO}")
        print("Nada a fazer. Se quiser baixar de novo, apague esse arquivo e rode o script outra vez.")
        return True

    for url in URLS:
        try:
            print(f"Baixando modelo de:\n  {url}\n(pode levar um minuto, é um arquivo de alguns MB)...")

            def progresso(bloco_num, tamanho_bloco, tamanho_total):
                if tamanho_total > 0:
                    pct = min(100, bloco_num * tamanho_bloco * 100 // tamanho_total)
                    print(f"\r  {pct}%", end="", flush=True)

            urllib.request.urlretrieve(url, DESTINO, reporthook=progresso)
            print()
            if os.path.getsize(DESTINO) > 1_000_000:
                print(f"\nPronto! Modelo salvo em: {DESTINO}")
                print("Agora é só reiniciar o site (pare e rode 'python app.py' de novo).")
                return True
            else:
                print("Download incompleto, tentando o próximo link...")
                os.remove(DESTINO)
        except Exception as e:
            print(f"Não deu certo com esse link ({e}). Tentando o próximo...")
            if os.path.exists(DESTINO):
                os.remove(DESTINO)

    print("\nNão consegui baixar automaticamente.")
    print("Baixe manualmente um arquivo 'pose_landmarker*.task' (procure por")
    print("'mediapipe pose landmarker task file download') e salve em:")
    print(f"  {DESTINO}")
    return False


if __name__ == "__main__":
    ok = baixar()
    sys.exit(0 if ok else 1)
