#ifndef SPACESHIP_H_
#define SPACESHIP_H_

#include <allegro5/allegro.h>


typedef struct {
	float x;
	float y;
	float heading;
	float speed;
	int gone;
	ALLEGRO_COLOR color;
} Spaceship;


void draw_spaceship(Spaceship *s);

#endif /* SPACESHIP_H_ */
