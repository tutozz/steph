cd bench/matrix/quality/prompt
export K=2
for m in qwen35 lfm25; do
./rep.sh $m g1 "B, 0 exemple, statut en clair et sortie encadrée" --sys b --fmt clear
./rep.sh $m g2 "B, 0 exemple, consigne finale Réponse en une ligne" --sys b --tail short
./rep.sh $m g3 "B, 2 exemples de catégories mêlées" --sys b --shots 2 --shotmode mixed
./rep.sh $m g4 "B sans règle au système, règle répétée en fin de message" --sys b0 --tail rule
./rep.sh $m g5 "B, statut en clair, consigne finale, 2 exemples mêlés" --sys b --fmt clear --tail short --shots 2 --shotmode mixed
done
