"""Importa uma fotografia do GE; executar manualmente para renovar a base."""
import concurrent.futures
import datetime
import json
import pathlib
import re
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = 'https://ge.globo.com/futebol/brasileirao-serie-a/'
BASE = 'https://api.globoesporte.globo.com/tabela/d1a37fa4-e948-43a6-ba53-ab24ab3a45b1/fase/fase-unica-campeonato-brasileiro-2026/rodada/'
REGULATION = 'https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/REC_Brasileiro_SA_rie_A_2026_v15_12_2025_final_02692c1077.pdf'

def download(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=35) as response:
        return response.read()

def round_data(number):
    path = ROOT / 'research' / f'round-{number}.json'
    data = json.loads(download(f'{BASE}{number}/jogos/'))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    if not isinstance(data, list) or len(data) != 10:
        raise ValueError(f'Rodada {number} incompleta')
    print(f'Rodada {number:02d}: {len(data)} jogos', flush=True)
    return number, data

(ROOT / 'research').mkdir(exist_ok=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    all_rounds = dict(pool.map(round_data, range(1, 39)))
html = download(SOURCE).decode('utf-8')
(ROOT / 'research' / 'ge.html').write_text(html)
match = re.search(r'const classificacao\s*=\s*(\{.*?\});', html, re.S)
if not match:
    raise ValueError('Classificação do GE não encontrada')
classification = json.loads(match.group(1))
assert len(classification['classificacao']) == 20
teams = []
for team in classification['classificacao']:
    teams.append(dict(id=team['equipe_id'], name=team['nome_popular'], shortName=team['sigla'], crest=team['escudo'], basePosition=team['ordem'], points=team['pontos'], played=team['jogos'], wins=team['vitorias'], draws=team['empates'], losses=team['derrotas'], goalsFor=team['gols_pro'], goalsAgainst=team['gols_contra'], goalDifference=team['saldo_gols'], form=team['ultimos_jogos']))
fixtures = []
for number, matches in sorted(all_rounds.items()):
    for game in matches:
        home, away = game['placar_oficial_mandante'], game['placar_oficial_visitante']
        started = game.get('jogo_ja_comecou', False)
        broadcast = ((game.get('transmissao') or {}).get('broadcast') or {}).get('id', '')
        status = 'finished' if home is not None and away is not None and (broadcast == 'ENCERRADA' or not broadcast) else 'live' if started else 'pending'
        fixtures.append(dict(id=game['id'], round=number, homeId=game['equipes']['mandante']['id'], awayId=game['equipes']['visitante']['id'], date=game.get('data_realizacao'), venue=(game.get('sede') or {}).get('nome_popular', 'Estádio a definir'), homeGoals=home, awayGoals=away, status=status))
assert len(fixtures) == len({f['id'] for f in fixtures}) == 380
for team in teams:
    finished = [f for f in fixtures if team['id'] in (f['homeId'], f['awayId']) and f['status'] == 'finished']
    assert len(finished) == team['played'], f"Contagem de jogos inconsistente: {team['name']}, {len(finished)} x {team['played']}"
    assert sum(team['id'] in (f['homeId'], f['awayId']) for f in fixtures) == 38
    assert team['points'] == team['wins'] * 3 + team['draws']
    assert team['played'] == team['wins'] + team['draws'] + team['losses']
    assert team['goalDifference'] == team['goalsFor'] - team['goalsAgainst']

crest_dir = ROOT / 'client' / 'public' / 'crests'
crest_dir.mkdir(parents=True, exist_ok=True)
def save_crest(team):
    content = download(team['crest'])
    if b'<svg' not in content:
        raise ValueError(f"Escudo SVG inválido: {team['name']}")
    (crest_dir / f"{team['id']}.svg").write_bytes(content)
    team['crest'] = f"/crests/{team['id']}.svg"
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    list(pool.map(save_crest, teams))
snapshot = dict(season=2026, source=SOURCE, collectedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(), currentRound=classification['rodada']['atual'], teams=teams, fixtures=fixtures, regulation=classification['edicao']['regulamento'], regulationUrl=REGULATION)
out = ROOT / 'client' / 'src' / 'data' / 'snapshot.json'
out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
print(f"Importação concluída: {len(teams)} clubes, {sum(f['status']=='finished' for f in fixtures)} jogos realizados, {sum(f['status']=='pending' for f in fixtures)} restantes.", flush=True)
